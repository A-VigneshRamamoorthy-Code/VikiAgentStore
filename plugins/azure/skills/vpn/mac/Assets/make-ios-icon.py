#!/usr/bin/env python3
"""Derive the full-bleed iOS app icon from the macOS icon art (AppIcon-mac.svg).

The macOS icon draws its own squircle with transparent padding and a drop shadow, as macOS
expects. iOS masks icons itself and needs an opaque, edge-to-edge square, so this drops the
squircle clip, shadow and outline and scales the art up so the squircle's content fills the
canvas. Writes AppIcon-ios.svg and renders the 1024px PNGs into ios/Assets.xcassets.

Needs rsvg-convert (brew install librsvg) and Pillow.
"""
import re, subprocess, os
from PIL import Image, ImageOps

here = os.path.dirname(os.path.abspath(__file__))
iconset = os.path.join(here, "../../ios/Assets.xcassets/AppIcon.appiconset")
src = open(os.path.join(here, "AppIcon-mac.svg")).read()

squircle = re.search(r'<clipPath id="sq"><path d="([^"]+)"/></clipPath>', src).group(1)
scale = 1024 / 824  # squircle spans 100…924
svg = src.replace(f'<clipPath id="sq"><path d="{squircle}"/></clipPath>', "")
svg = re.sub(r'<g filter="url\(#ish\)">.*?</g>\n', "", svg, flags=re.S)                  # drop shadow
svg = svg.replace(f'<path d="{squircle}" fill="url(#gloss)"/>',
                  '<rect x="-200" y="-200" width="1424" height="1424" fill="url(#gloss)"/>')
svg = svg.replace(f'<path d="{squircle}" fill="none" stroke="#fff" stroke-opacity="0.18" stroke-width="3"/>', "")
svg = svg.replace('<g clip-path="url(#sq)">',
                  f'<rect width="1024" height="1024" fill="#0B1410"/>'
                  f'<g transform="translate(512 512) scale({scale:.5f}) translate(-512 -512)">')
assert squircle not in svg and "#sq" not in svg
open(os.path.join(here, "AppIcon-ios.svg"), "w").write(svg)

png = os.path.join(iconset, "AppIcon-1024.png")
subprocess.run(["rsvg-convert", "-w", "1024", "-h", "1024", "-b", "#0B1410", "-o", png,
                os.path.join(here, "AppIcon-ios.svg")], check=True)
light = Image.open(png).convert("RGB")
light.save(png)
# Tinted variant: iOS recolours a grayscale image, so keep only luminance on black.
ImageOps.autocontrast(ImageOps.grayscale(light), cutoff=1).convert("RGB").save(
    os.path.join(iconset, "AppIcon-1024-tinted.png"))
