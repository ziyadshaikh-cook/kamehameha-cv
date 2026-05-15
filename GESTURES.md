# Gesture Reference

This project uses **MediaPipe Hands** (not Pose). It detects 21 landmarks per hand.

## Key Landmarks Used

| Index | Name              | Role in this project          |
|-------|-------------------|-------------------------------|
| 0     | WRIST             | Distance between hands, ball center |
| 9     | MIDDLE_FINGER_MCP | Palm base — used for smoother ball center |

## Detection Logic

### Cupped Hands (Charging)
- Both hands visible
- Distance between wrist landmarks < `CUP_DIST_THRESHOLD` (default 220px)
- Hands held at chest level

### Push to Fire
- Ball center position tracked over last 0.25 seconds
- If movement speed exceeds `VELOCITY_FIRE_THRESH` (default 75 px/sec) → beam fires
- Works from any angle — sideways, forward, upward

### Beam Direction
- Computed from bottom-center of frame (body reference) → ball position at fire moment
- Mathematically cannot backfire toward the body
- Blended 35/65 with push velocity direction for aiming accuracy

## State Machine

```
IDLE ──(both hands cupped)──► CHARGING
CHARGING ──(hold 3 sec)──────► READY
CHARGING ──(push at ≥35%)────► FIRING
READY ──(push)───────────────► FIRING
FIRING ──(1.4 sec elapsed)───► IDLE

Any state ──(hands lost + charge decays)──► IDLE
```

## Tuning Parameters (top of app.py)

| Constant              | Default | What it controls                        |
|-----------------------|---------|-----------------------------------------|
| `CHARGE_HOLD_NEEDED`  | 3.0s    | Time to reach 100% charge              |
| `BEAM_DURATION`       | 1.4s    | How long beam stays on screen          |
| `CUP_DIST_THRESHOLD`  | 220px   | Max wrist distance to count as cupped  |
| `FIRE_CHARGE_MIN`     | 0.35    | Minimum charge needed to fire          |
| `VELOCITY_FIRE_THRESH`| 75px/s  | Push speed needed to trigger beam      |
| `PUSH_WINDOW`         | 0.25s   | Time window for velocity calculation   |

If cupping isn't detecting → raise `CUP_DIST_THRESHOLD` to 260  
If beam fires too easily → raise `VELOCITY_FIRE_THRESH` to 120  
If beam never fires → lower `VELOCITY_FIRE_THRESH` to 50  
Check the debug bar at screen bottom for live distance and speed values.