import React from 'react';
import {PURSUIT as P, mix, shade} from '../lib/palette.js';

/**
 * Broadcast furniture.
 *
 * Modelled on the news graphics reference supplied with the brief: a pale
 * headline slab, a saturated red lower third under it, blocky channel marks
 * bottom-left and a translucent location tag bottom-right.
 *
 * These are drawn in **screen space**, not board space, and that distinction is
 * the entire reason they work. A chyron belongs to the broadcast, not to the
 * world being broadcast, so it must not inherit the camera transform -- if it
 * parallaxes with the set, the joke that a real channel is covering this
 * non-event collapses immediately.
 */

const FACE = '"Helvetica Neue", Helvetica, Arial, sans-serif';

/** Wipe in from the left, hold, and wipe out. `t` is shot-local seconds. */
const wipe = (t, dur, lead = 0.45, tail = 0.5) => {
  if (t < 0) return 0;
  if (t < lead) return t / lead;
  if (t > dur - tail) return Math.max(0, (dur - t) / tail);
  return 1;
};

export const NewsLower = ({t, dur, headline, kicker}) => {
  const k = wipe(t, dur);
  const ease = 1 - Math.pow(1 - k, 3);
  return (
    <div style={{position: 'absolute', left: '3.2%', right: '3.2%', bottom: '11%',
                 transformOrigin: 'left center', transform: `scaleX(${ease})`,
                 opacity: k > 0 ? 1 : 0, fontFamily: FACE}}>
      {headline && (
        <div style={{background: 'rgba(238,238,236,0.96)', color: '#15171d',
                     padding: '0.9% 1.6%', fontSize: '2.9vw', fontWeight: 700,
                     letterSpacing: '-0.01em', lineHeight: 1.15,
                     borderBottom: '0.28vw solid rgba(0,0,0,0.10)'}}>
          {headline}
        </div>
      )}
      <div style={{background: P.accent, color: '#ffffff', padding: '1.1% 1.6%',
                   fontSize: '3.4vw', fontWeight: 800, letterSpacing: '0.005em',
                   lineHeight: 1.1, display: 'flex', alignItems: 'center', gap: '1.4%'}}>
        {kicker && (
          <span style={{background: '#ffffff', color: P.accent, fontSize: '2.0vw',
                        fontWeight: 900, padding: '0.35% 0.9%', letterSpacing: '0.06em',
                        whiteSpace: 'nowrap'}}>
            {kicker}
          </span>
        )}
        <span>{headline ? 'LIVE' : ''}</span>
      </div>
    </div>
  );
};

/** The channel mark: four letter tiles, deliberately blocky. */
export const ChannelMark = ({letters = ['V', 'N', 'N']}) => (
  <div style={{position: 'absolute', left: '3.2%', bottom: '3.4%', display: 'flex', gap: '0.45vw'}}>
    {letters.map((ch, i) => (
      <div key={i} style={{background: '#ffffff', color: '#15171d', width: '3.1vw', height: '3.1vw',
                           display: 'flex', alignItems: 'center', justifyContent: 'center',
                           fontFamily: FACE, fontWeight: 800, fontSize: '2.2vw'}}>
        {ch}
      </div>
    ))}
  </div>
);

/** Where we supposedly are. */
export const LocationTag = ({text}) => (
  <div style={{position: 'absolute', right: '3.2%', bottom: '3.4%',
               background: 'rgba(70,74,82,0.82)', color: '#ffffff',
               padding: '0.55% 1.3%', fontFamily: FACE, fontWeight: 700,
               fontSize: '2.4vw', letterSpacing: '0.01em'}}>
    {text}
  </div>
);

/** The clock, because a live broadcast always has one. */
export const LiveClock = ({t, start = 631}) => {
  const total = Math.floor(start + t);
  const mm = String(Math.floor(total / 60) % 100).padStart(2, '0');
  const ss = String(total % 60).padStart(2, '0');
  return (
    <div style={{position: 'absolute', left: '3.2%', top: '4%', display: 'flex',
                 alignItems: 'center', gap: '0.8vw', fontFamily: FACE}}>
      <div style={{width: '1.05vw', height: '1.05vw', borderRadius: '50%',
                   background: P.accent, opacity: Math.floor(t * 1.4) % 2 ? 0.35 : 1}} />
      <div style={{color: '#ffffff', fontWeight: 800, fontSize: '2.5vw',
                   textShadow: '0 0.15vw 0.4vw rgba(0,0,0,0.45)'}}>
        {mm}:{ss}
      </div>
    </div>
  );
};

/**
 * The tracking ring, and the film's best single gag.
 *
 * It is captioned SUSPECT VEHICLE and it is drawn around a police car. Nothing
 * in the picture says the chopper is wrong; the audience does that work.
 */
export const TrackingRing = ({t, label, x = 50, y = 50, r = 13}) => {
  const pulse = 1 + Math.sin(t * 4.2) * 0.035;
  const dash = (t * 26) % 12;
  return (
    <div style={{position: 'absolute', left: 0, top: 0, width: '100%', height: '100%'}}>
      <svg viewBox="0 0 100 56.25" style={{width: '100%', height: '100%'}} preserveAspectRatio="none">
        <g transform={`translate(${x} ${y}) scale(${pulse})`}>
          <ellipse rx={r} ry={r * 0.62} fill="none" stroke={P.accent} strokeWidth={0.42}
                   strokeDasharray="7 5" strokeDashoffset={-dash} opacity={0.95} />
          <ellipse rx={r * 0.82} ry={r * 0.51} fill="none" stroke="#ffffff" strokeWidth={0.16} opacity={0.5} />
          <path d={`M ${-r} 0 L ${-r * 0.72} 0 M ${r} 0 L ${r * 0.72} 0
                    M 0 ${-r * 0.62} L 0 ${-r * 0.44} M 0 ${r * 0.62} L 0 ${r * 0.44}`}
                stroke={P.accent} strokeWidth={0.3} />
        </g>
      </svg>
      {label && (
        <div style={{position: 'absolute', left: `${x - r}%`, top: `${((y - r * 0.62 - 3.6) / 56.25) * 100}%`,
                     background: 'rgba(18,20,26,0.88)', color: '#ffffff', fontFamily: FACE,
                     fontWeight: 800, fontSize: '1.5vw', padding: '0.3% 0.75%',
                     letterSpacing: '0.08em', whiteSpace: 'nowrap'}}>
          {label}
        </div>
      )}
    </div>
  );
};

/** A map inset: grid, a marker that drifts, and no useful information at all. */
export const MapInset = ({t, marker = [0.5, 0.5]}) => {
  const drift = Math.sin(t * 0.9) * 0.02;
  return (
    <div style={{position: 'absolute', right: '4%', top: '9%', width: '24%', aspectRatio: '4 / 3',
                 background: 'rgba(20,23,29,0.92)', border: '0.22vw solid rgba(255,255,255,0.35)'}}>
      <svg viewBox="0 0 100 75" style={{width: '100%', height: '100%'}}>
        {Array.from({length: 7}, (_, i) => (
          <line key={`h${i}`} x1={0} y1={i * 12.5} x2={100} y2={i * 12.5}
                stroke="#ffffff" strokeWidth={0.3} opacity={0.16} />
        ))}
        {Array.from({length: 9}, (_, i) => (
          <line key={`v${i}`} x1={i * 12.5} y1={0} x2={i * 12.5} y2={75}
                stroke="#ffffff" strokeWidth={0.3} opacity={0.16} />
        ))}
        <path d="M 0 46 L 34 46 L 42 30 L 100 30" stroke={mix(P.accent2, '#ffffff', 0.3)}
              strokeWidth={1.1} fill="none" opacity={0.75} />
        <g transform={`translate(${(marker[0] + drift) * 100} ${marker[1] * 75})`}>
          <circle r={5.2} fill={P.accent2} opacity={0.22} />
          <circle r={2.1} fill={P.accent2} stroke="#ffffff" strokeWidth={0.5} />
        </g>
      </svg>
    </div>
  );
};
