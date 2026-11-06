import math, sys
def dots(cx, cy, rings, a0=-88, a1=-2):
    out=[]
    for r, n, dr in rings:
        for i in range(n):
            a=math.radians(a0+(a1-a0)*i/(n-1))
            out.append((cx+r*math.cos(a), cy+r*math.sin(a), dr, r, i, n))
    return out
def icon(size=1024, simple=False):
    cx, cy = 300, 724
    rings=[(180,4,25),(310,6,25),(440,8,25)]
    els=[]
    for x,y,dr,r,i,n in dots(cx,cy,rings):
        if r==440 and i==5:
            els.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="78" fill="url(#glow)"/>')
            els.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="38" fill="#ffc24a"/>')
        else:
            op = {180:1, 310:.9, 440:.75}[r]
            els.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{dr}" fill="#fff" fill-opacity="{op}"/>')
    body="\n    ".join(els)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#3a95ff"/><stop offset=".55" stop-color="#0a66c2"/><stop offset="1" stop-color="#0a3f86"/>
    </linearGradient>
    <radialGradient id="sheen" cx=".3" cy=".15" r=".8">
      <stop offset="0" stop-color="#fff" stop-opacity=".22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glow"><stop offset="0" stop-color="#ffc24a" stop-opacity=".55"/><stop offset="1" stop-color="#ffc24a" stop-opacity="0"/></radialGradient>
    <filter id="sh" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#000" flood-opacity=".28"/></filter>
  </defs>
  <g filter="url(#sh)">
    <rect x="100" y="100" width="824" height="824" rx="186" fill="url(#bg)"/>
    <rect x="100" y="100" width="824" height="824" rx="186" fill="url(#sheen)"/>
    <rect x="101" y="101" width="822" height="822" rx="185" fill="none" stroke="#fff" stroke-opacity=".12" stroke-width="2"/>
  </g>
  <circle cx="{cx}" cy="{cy}" r="58" fill="#fff"/>
    {body}
</svg>'''
open('icon.svg','w').write(icon())
