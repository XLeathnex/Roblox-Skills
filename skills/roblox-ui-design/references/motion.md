# Motion

Motion is half of how a UI feels. Two levels: everyday feedback, and a signature entrance that makes a screen memorable.

## Everyday feedback (always)

- `"motion": "button"` on buttons: hover and press response. `"motion": "panel"` on panels: animated open and close. `meta.motion` sets the character: `bouncy` (cartoon), `snappy` (clean, competitive), `calm` (horror, cinematic).
- Stagger repeated things. Give each card or row an `enter` with a rising `delay` (0.04-0.07s apart) so a grid lands as a wave instead of popping all at once.
- Idle life in small doses: `"loop": {"bob": 6, "period": 2.4}` on a featured item, `{"spin": 20}` on a sunburst, `{"pulse": 0.04}` on the one button you want pressed.

## Choreography keys

Any GuiObject can take these. They play when its panel opens (or at start for always-on HUD). Offsets are design pixels relative to the object's resting place.

```json
"enter": {"from": [0, -700], "delay": 0.2, "dur": 0.5, "ease": "Back", "rot": -8, "scale": 0.7, "fade": true, "reveal": "down"},
"leave": {"at": 1.4, "to": [1500, -300], "dur": 0.7, "rot": 12, "fade": true},
"loop":  {"bob": 8, "sway": 3, "pulse": 0.04, "spin": 30, "period": 2.4}
```

- `enter`: where it comes from. `from` flies it in; `scale` and `rot` are its starting size and tilt; `fade` starts invisible; `reveal: "down" | "right"` unrolls it like a blind or a scroll (give that node pixel-sized children). `ease`: Back (overshoot), Quint/Quad (smooth), Elastic, Bounce, Sine, Linear.
- `leave`: a prop that exits. `at` is seconds after the panel opens; it moves by `to`, then hides. Use it for carriers, curtains, wipes.
- `loop`: idle motion after it has landed.
- `from` and `to` are ignored on direct children of a list or grid (the layout owns their position); use `scale` and `fade` there, or wrap the child in a fixed holder.

See it without Studio: `python3 <skill>/scripts/rbxui storyboard ui.json` renders six frames of the sequence (`--times 0,0.3,0.6,1,1.5,2.2` to choose them). Read the frames like a film strip: is each beat clear, does anything pass through anything, does it end tidy?

## Signature entrances (when the user wants something special)

A signature entrance stages the opening of a screen as a small scene from the game's world: things that belong to the game bring the UI in. The UI still ends as the same clean, usable layout; the scene is how it arrives, in one to two and a half seconds.

How to design one:

1. **Find the actor.** What in this game moves, carries, grows, opens or builds? A crane lowers the shop sign in a construction tycoon. Fish swim the header in and scatter. A drawbridge drops and the panel is the gate. Vines grow up the frame, then bloom into item cards. A printer feeds the receipt-shaped list out line by line. Pick the idea only this game could have.
2. **Write three or four beats**, each 0.3-0.6s, overlapping slightly:
   - *arrival*: the actor enters carrying or pulling the first piece (usually the header);
   - *handoff*: it lets go or leaves (`leave`), and the main body appears from the piece it delivered (`reveal`, or `enter` from that edge);
   - *population*: the contents land in their places, staggered, each arriving in a way that fits the idea;
   - *settle*: one small idle loop keeps the scene alive.
3. **Draw the actors** as images (assets.md). They are props: outside the layout, positioned by pixels, usually with both `enter` and `leave`.
4. **Keep it usable.** Buttons are tappable by the end of the body's reveal; nothing covers the content once settled; total length under about 2.5s; closing is quick and plain. The runtime skips all of it for players with reduced motion.
5. **Storyboard it** and fix the beats that are muddy.

Order by `delay`. A typical timing: arrival 0.0-0.6, handoff 0.5-1.0, population 0.8-1.6 staggered, actors gone by 1.6.

Do not animate for its own sake: one strong idea, executed cleanly, beats five effects.
