#!/bin/sh
# LeapVPN server firewall: NAT out, keep tunnel peers away from the VM itself
# and from Azure's metadata/identity endpoints (they would otherwise be able
# to mint the VM's managed-identity token), and black-hole IPv6 so clients
# never leak it outside the tunnel.
OUT=$(ip -4 route show default | awk '{print $5; exit}')
if [ "$1" = down ]; then A=-D; else A=-A; fi
r() { "$@" 2>/dev/null || [ "$A" = -D ]; }

r iptables -t nat $A POSTROUTING -s 10.66.0.0/24 -o "$OUT" -j MASQUERADE
r iptables -t mangle $A FORWARD -o wg0 -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
r iptables -t mangle $A FORWARD -i wg0 -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
r iptables $A FORWARD -i wg0 -d 169.254.169.254 -j DROP
r iptables $A FORWARD -i wg0 -d 168.63.129.16 -j DROP
r iptables $A FORWARD -i wg0 -d 10.0.0.0/8 -j DROP
# Home exits (vx<port> tun devices, see agent.py) carry TCP only: reject UDP
# such as QUIC so apps fall back to TCP instead of leaking via Azure or hanging.
r iptables $A FORWARD -i wg0 -o vx+ -p udp -j REJECT --reject-with icmp-port-unreachable
r iptables $A FORWARD -i wg0 -o vx+ -j ACCEPT
r iptables $A FORWARD -i wg0 -o "$OUT" -j ACCEPT
r iptables $A FORWARD -o wg0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
r iptables $A INPUT -i wg0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
r iptables $A INPUT -i wg0 -p icmp -j ACCEPT
r iptables $A INPUT -i wg0 -j DROP
r ip6tables $A FORWARD -i wg0 -j REJECT
r ip6tables $A INPUT -i wg0 -p ipv6-icmp -j ACCEPT
r ip6tables $A INPUT -i wg0 -j DROP
exit 0
