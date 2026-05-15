# ⚡ kamehameha-cv

Real-time Goku-style energy blast using your webcam. Cup your hands, charge the ki ball, push forward — beam fires.

Built with Python, OpenCV, and MediaPipe Hands. No ML training. No special hardware. Just a webcam and your hands.

---

## How It Works

MediaPipe detects 21 landmarks on each hand at ~30fps. The app tracks the distance between your wrists to detect the cupped-hands pose, then monitors the velocity of your hand movement to detect the push/fire gesture. The beam direction is locked at the moment you fire, computed from your body position outward — so it physically cannot backfire toward you.

Visual effects are built entirely with OpenCV: layered additive glow circles for the ki ball, orbiting particle arcs during charge buildup, and a multi-layer beam drawn with animated shimmer.

---

## Requirements

- Python 3.9, 3.10, or 3.11 (MediaPipe does **not** support 3.12+ as of now)
- Webcam
- Conda (recommended) or standard Python venv

---

## Installation

### Step 1 — Clone the repo

```bash
https://github.com/ziyadshaikh-cook/kamehameha-cv.git
```

### Step 2 — Create environment

**With Conda (recommended):**
```bash
conda create -p venv python==3.10
conda activate ./venv
```

**With venv:**
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Run

```bash
python app.py
```

Press `Q` to quit. Press `D` to toggle the debug overlay.

---

## The Gesture — Step by Step

This is the exact sequence to charge and fire:

**1. Get in position**  
Stand about 1–1.5 meters from your webcam. Make sure both hands are clearly visible. Good lighting matters — MediaPipe struggles in dark rooms.

**2. Cup your hands (charging begins)**  
Hold both hands close together at your lower chest, as if you're carrying a small invisible sphere between them. One hand forms a platform underneath, the other curves over the top. The screen should show `CHARGING` and a ball will appear between your hands.

**3. Hold the pose (charge builds)**  
Keep your hands cupped. The ball grows brighter and larger over 3 seconds. Orbiting particles appear around it as charge increases. A charge bar on screen shows your percentage. You can hold partial charge — minimum 35% is needed to fire.

**4. Compress (optional — looks great)**  
As the ball fills up, subtly bring your hands closer and tighten your grip. Your elbows can pull in toward your torso. The ball responds visually to the charge level, getting more intense.

**5. Aim and shift**  
Once charged (or even mid-charge), rotate your torso slightly toward your target direction. The beam will lock to wherever your hands are positioned when you push.

**6. Push forward to fire**  
Make a deliberate pushing motion — shove the ball forward in any direction. The velocity of that push triggers the beam. The beam fires outward from your hands in the direction you pushed, away from your body.

> **Note:** You do not need to spread your arms or change hand shape to fire. The trigger is purely the speed of the push movement. A quick, decisive push fires it. A slow drift does not.

---

## Debug Mode

Press `D` while running to toggle the debug overlay. It shows:

- Live wrist distance in pixels (tells you if cupping is being detected)
- Live push speed in px/sec (tells you if your fire gesture is strong enough)
- The thresholds your current config is using
- Hand skeleton drawn on both hands

Use this to tune the constants at the top of `app.py` for your specific webcam distance and room setup.

---

## File Structure

```
kamehameha-cv/
├── app.py            # Main application — all logic and effects
├── GESTURES.md       # Hand landmark reference and state machine docs
├── requirements.txt  # Python dependencies
├── README.md         # This file
└── .gitignore        # Excludes venv, pycache, etc.
```

---

## Tech Stack

| Library      | Version   | Purpose                            |
|--------------|-----------|------------------------------------|
| OpenCV       | 4.9.0.80  | Camera capture, drawing, display   |
| MediaPipe    | 0.10.14   | Real-time hand landmark detection  |
| NumPy        | 1.26.4    | Array ops, glow effect math        |

---

## Tuning

If detection or firing feels off, edit these constants at the top of `app.py`:

| Constant               | Default | Increase if...                        | Decrease if...                    |
|------------------------|---------|---------------------------------------|-----------------------------------|
| `CUP_DIST_THRESHOLD`   | 220px   | Cupping never triggers                | Triggering when hands not cupped  |
| `VELOCITY_FIRE_THRESH` | 75px/s  | Beam fires from small movements       | Push never triggers the beam      |
| `CHARGE_HOLD_NEEDED`   | 3.0s    | Want faster charge                    | Want to hold longer               |
| `FIRE_CHARGE_MIN`      | 0.35    | Want to require more charge to fire   | Want to fire from very low charge |

Run with `D` key active and watch the debug bar — it shows live values so you know exactly what to set.

---

## Known Limitations

- Requires decent lighting. MediaPipe hand detection degrades significantly in low-light conditions.
- Works best when both hands are unobstructed and facing roughly toward the camera.
- Python 3.12+ is not supported by MediaPipe 0.10.14. Use 3.9–3.11.
- Tested on Windows. Should work on macOS and Linux — open an issue if it doesn't.

---

## License

MIT
