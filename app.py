import cv2
import mediapipe as mp
import numpy as np
import time
from collections import deque

# ── MediaPipe ─────────────────────────────────────────────────────
mp_hands = mp.solutions.hands
hands_detector = mp_hands.Hands(
    max_num_hands=2,
    min_detection_confidence=0.75,
    min_tracking_confidence=0.65
)
mp_draw = mp.solutions.drawing_utils

# ── Constants — tune these if needed ──────────────────────────────
CHARGE_HOLD_NEEDED   = 3.0    # seconds for 100% charge
BEAM_DURATION        = 1.4    # seconds beam displays
CUP_DIST_THRESHOLD   = 220    # px — wrists closer than this = cupped
FIRE_CHARGE_MIN      = 0.35   # minimum charge % to allow firing
VELOCITY_FIRE_THRESH = 75     # px/sec push speed to trigger fire
PUSH_WINDOW          = 0.25   # seconds of history used for velocity calc

# ── State ─────────────────────────────────────────────────────────
state              = "IDLE"
charge_level       = 0.0
charge_start_time  = None
fire_start_time    = None
locked_beam_dir    = None
locked_ball_center = None

pos_history   = deque(maxlen=25)   # (time, x, y) for velocity
center_smooth = deque(maxlen=10)   # position smoother
DEBUG = True


# ── Helpers ───────────────────────────────────────────────────────

def smooth_center(pt):
    center_smooth.append(pt)
    return (int(np.mean([p[0] for p in center_smooth])),
            int(np.mean([p[1] for p in center_smooth])))


def get_velocity(now):
    recent = [(t, x, y) for t, x, y in pos_history if now - t < PUSH_WINDOW]
    if len(recent) < 3:
        return 0.0, 0.0
    dt = recent[-1][0] - recent[0][0]
    if dt < 0.01:
        return 0.0, 0.0
    return (recent[-1][1] - recent[0][1]) / dt, \
           (recent[-1][2] - recent[0][2]) / dt


def get_beam_direction(ball_center, fw, fh, velocity=None):
    """
    Direction is computed from body position (bottom-center of frame)
    to ball center. This ALWAYS points away from the body — beam
    can never backfire.
    If a strong push velocity exists, blend it in for accuracy.
    """
    bx, by = ball_center
    body_ref = (fw // 2, int(fh * 0.92))          # approximate body base
    dx = bx - body_ref[0]
    dy = by - body_ref[1]                          # will be negative (upward)
    mag = max(1.0, np.sqrt(dx**2 + dy**2))
    body_dir = (dx / mag, dy / mag)

    if velocity:
        vx, vy = velocity
        vmag = np.sqrt(vx**2 + vy**2)
        if vmag > 20:
            vx_n, vy_n = vx / vmag, vy / vmag
            bx_ = body_dir[0] * 0.35 + vx_n * 0.65
            by_ = body_dir[1] * 0.35 + vy_n * 0.65
            bmag = max(0.001, np.sqrt(bx_**2 + by_**2))
            blended = (bx_ / bmag, by_ / bmag)
            # Safety: if blended direction points strongly downward (backfire risk),
            # fall back to pure body_dir
            if blended[1] > 0.5:
                return body_dir
            return blended

    return body_dir


def draw_glowing_ball(frame, center, radius, intensity, phase=0.0):
    cx, cy = int(center[0]), int(center[1])
    overlay = np.zeros_like(frame, dtype=np.float32)
    ic = min(1.0, max(0.0, intensity))
    r  = int(radius * (1 + np.sin(phase) * 0.06 * ic))

    # 8 glow rings — additive blend
    for i in range(8, 0, -1):
        gr = int(r * (1 + i * 0.55))
        a  = ic * 0.13 * (9 - i) / 8
        # Color shifts: dim blue → full white-blue
        cv2.circle(overlay, (cx, cy), gr,
                   (a * 100 * (1 + ic), a * 180, a * 255), -1)

    # Core ball
    cv2.circle(overlay, (cx, cy), r,
               (int(155 + 100*ic), int(200 + 55*ic), 255), -1)
    # Inner bright ring
    cv2.circle(overlay, (cx, cy), max(3, int(r * 0.52)),
               (int(215 + 40*ic), int(232 + 23*ic), 255), -1)
    # White hot center
    cv2.circle(overlay, (cx, cy), max(2, int(r * 0.26)),
               (255, 255, 255), -1)

    np.clip(frame.astype(np.float32) + overlay, 0, 255,
            out=overlay)
    frame[:] = overlay.astype(np.uint8)


def draw_charge_aura(frame, center, charge, now):
    """Orbiting ki particles around ball — quantity and orbit grow with charge."""
    if charge < 0.15:
        return
    cx, cy = int(center[0]), int(center[1])
    n = int(charge * 10)

    for i in range(n):
        angle    = now * 2.8 + i * (2 * np.pi / max(1, n))
        orbit_r  = int(55 + charge * 60 + np.sin(now * 3 + i) * 12)
        px = int(cx + np.cos(angle) * orbit_r)
        py = int(cy + np.sin(angle) * orbit_r * 0.58)   # elliptical orbit
        pr = max(2, int(3 + charge * 4))
        alpha = 0.35 + charge * 0.3
        ov = frame.copy()
        cv2.circle(ov, (px, py), pr, (180, 215, 255), -1)
        cv2.addWeighted(ov, alpha, frame, 1 - alpha, 0, frame)


def draw_beam(frame, start, direction, progress, now):
    sx, sy = int(start[0]), int(start[1])
    dx, dy = direction
    fh, fw = frame.shape[:2]

    max_len = int(np.sqrt(fw**2 + fh**2))
    cur_len = int(max_len * min(1.0, progress * 2.8))   # extends fast
    ex = int(sx + dx * cur_len)
    ey = int(sy + dy * cur_len)

    fade    = max(0.15, 1.0 - progress * 0.55)
    shimmer = 0.88 + np.sin(now * 28) * 0.12            # animated shimmer
    overlay = np.zeros_like(frame, dtype=np.float32)

    for thickness, (b, g, r_) in [
        (130, (0.07, 0.20, 0.68)),
        (70,  (0.18, 0.48, 0.94)),
        (32,  (0.48, 0.74, 1.00)),
        (13,  (0.80, 0.90, 1.00)),
        (4,   (1.00, 1.00, 1.00)),
    ]:
        cv2.line(overlay, (sx, sy), (ex, ey),
                 (b*255*shimmer, g*255, r_*255), thickness)

    np.clip(frame.astype(np.float32) + overlay * fade, 0, 255,
            out=overlay)
    frame[:] = overlay.astype(np.uint8)


def apply_vignette(frame, charge):
    """Screen darkens as charge builds — cinematic feel."""
    if charge < 0.2:
        return
    darkness = charge * 0.44
    dark = np.zeros_like(frame)
    cv2.addWeighted(frame, 1 - darkness, dark, darkness, 0, frame)


# ── Camera ────────────────────────────────────────────────────────
cap        = cv2.VideoCapture(0)
prev_time  = time.time()
frame_count = 0

print("=" * 40)
print("  GOKU BEAM")
print("=" * 40)
print("  Cup both hands at chest → hold to charge")
print("  Push forward quickly to FIRE")
print("  Q = quit  |  D = toggle debug")
print("=" * 40)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.flip(frame, 1)
    fh, fw = frame.shape[:2]
    now = time.time()
    dt  = now - prev_time
    prev_time  = now
    frame_count += 1

    rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands_detector.process(rgb)

    both_hands  = (results.multi_hand_landmarks and
                   len(results.multi_hand_landmarks) == 2)
    wrist_dist  = 9999
    ball_center = None

    if both_hands:
        h1 = results.multi_hand_landmarks[0].landmark
        h2 = results.multi_hand_landmarks[1].landmark

        # Wrist = 0,  palm base (middle MCP) = 9
        w1 = (int(h1[0].x * fw), int(h1[0].y * fh))
        w2 = (int(h2[0].x * fw), int(h2[0].y * fh))
        p1 = (int(h1[9].x * fw), int(h1[9].y * fh))
        p2 = (int(h2[9].x * fw), int(h2[9].y * fh))

        wrist_dist = np.sqrt((w1[0]-w2[0])**2 + (w1[1]-w2[1])**2)
        wrist_mid  = ((w1[0]+w2[0])//2, (w1[1]+w2[1])//2)
        palm_mid   = ((p1[0]+p2[0])//2, (p1[1]+p2[1])//2)
        raw_c      = ((wrist_mid[0]+palm_mid[0])//2,
                      (wrist_mid[1]+palm_mid[1])//2)
        ball_center = smooth_center(raw_c)

        pos_history.append((now, ball_center[0], ball_center[1]))
        vx, vy = get_velocity(now)
        speed   = np.sqrt(vx**2 + vy**2)
        cupped  = wrist_dist < CUP_DIST_THRESHOLD
        is_push = speed > VELOCITY_FIRE_THRESH

        if DEBUG and frame_count % 20 == 0:
            print(f"dist={wrist_dist:.0f}  cupped={cupped}  "
                  f"speed={speed:.0f}px/s  state={state}  "
                  f"charge={int(charge_level*100)}%")

        for hand_lms in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(frame, hand_lms,
                                   mp_hands.HAND_CONNECTIONS)

        # ── State machine ──────────────────────────────────────────
        if state == "IDLE":
            if cupped:
                state = "CHARGING"
                charge_start_time = now
                charge_level = 0.0
                center_smooth.clear()
                pos_history.clear()

        elif state == "CHARGING":
            charge_level = min(1.0, (now - charge_start_time) / CHARGE_HOLD_NEEDED)

            if not cupped:
                charge_level = max(0.0, charge_level - dt * 0.55)
                if charge_level <= 0.0:
                    state = "IDLE"

            elif is_push and charge_level >= FIRE_CHARGE_MIN:
                locked_beam_dir    = get_beam_direction(
                    ball_center, fw, fh, (vx, vy))
                locked_ball_center = ball_center
                state              = "FIRING"
                fire_start_time    = now

            elif charge_level >= 1.0:
                state = "READY"
                locked_beam_dir = get_beam_direction(ball_center, fw, fh)

        elif state == "READY":
            # Keep direction fresh as person aims
            locked_beam_dir = get_beam_direction(ball_center, fw, fh)

            if is_push:
                locked_beam_dir    = get_beam_direction(
                    ball_center, fw, fh, (vx, vy))
                locked_ball_center = ball_center
                state              = "FIRING"
                fire_start_time    = now
            elif not cupped:
                charge_level = max(0.0, charge_level - dt * 0.8)
                if charge_level <= 0.0:
                    state = "IDLE"

        elif state == "FIRING":
            if now - fire_start_time > BEAM_DURATION:
                state              = "IDLE"
                charge_level       = 0.0
                locked_beam_dir    = None
                locked_ball_center = None
                center_smooth.clear()
                pos_history.clear()

    else:
        # Lost hand tracking
        if state in ("CHARGING", "READY"):
            charge_level = max(0.0, charge_level - dt * 0.7)
            if charge_level <= 0.0:
                state = "IDLE"
        # FIRING continues until timer expires naturally

    # ── Cinematic darkening ────────────────────────────────────────
    if state in ("CHARGING", "READY"):
        apply_vignette(frame, charge_level)

    # ── Draw effects ───────────────────────────────────────────────
    if state in ("CHARGING", "READY") and ball_center:
        radius = int(16 + charge_level * 85)
        if state == "READY":
            radius = int(radius * (1 + np.sin(now * 10) * 0.09))
        draw_charge_aura(frame, ball_center, charge_level, now)
        draw_glowing_ball(frame, ball_center, radius, charge_level,
                          phase=now * 9)

    elif state == "FIRING":
        elapsed    = now - fire_start_time
        progress   = elapsed / BEAM_DURATION
        intensity  = max(0.0, 1.0 - progress * 0.7)
        center_use = locked_ball_center or ball_center

        if center_use and locked_beam_dir:
            draw_beam(frame, center_use, locked_beam_dir, progress, now)
            ball_r = max(3, int(38 * (1.0 - min(1.0, progress * 1.3))))
            if ball_r > 3:
                draw_glowing_ball(frame, center_use, ball_r, intensity)

    # ── HUD ────────────────────────────────────────────────────────
    col = {
        "IDLE":     (140, 140, 140),
        "CHARGING": (0,   200, 255),
        "READY":    (0,   255, 80),
        "FIRING":   (80,  120, 255)
    }.get(state, (255, 255, 255))

    cv2.putText(frame, state, (20, 48),
                cv2.FONT_HERSHEY_DUPLEX, 1.4, col, 2)

    hcol  = (0, 255, 80) if both_hands else (0, 60, 220)
    hlabel = "HANDS OK" if both_hands else "SHOW BOTH HANDS"
    cv2.putText(frame, hlabel, (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, hcol, 1)

    if state in ("CHARGING", "READY"):
        bw_ = 280
        filled = int(charge_level * bw_)
        cv2.rectangle(frame, (20, 96), (20+bw_, 113), (22, 22, 22), -1)
        bar_b = int(255 * (1 - charge_level))
        cv2.rectangle(frame, (20, 96), (20+filled, 113),
                      (bar_b, 170, 255), -1)
        cv2.putText(frame, f"{int(charge_level*100)}%",
                    (20+bw_+8, 111),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 1)

    if state == "READY" and int(now * 2) % 2 == 0:
        cv2.putText(frame, "PUSH FORWARD TO FIRE",
                    (fw//2 - 175, fh - 25),
                    cv2.FONT_HERSHEY_DUPLEX, 0.82, (0, 255, 80), 2)

    if DEBUG and both_hands:
        vxd, vyd = get_velocity(now)
        spd = np.sqrt(vxd**2 + vyd**2)
        cv2.putText(frame,
                    f"dist:{wrist_dist:.0f}px  "
                    f"speed:{spd:.0f}px/s  "
                    f"fire_thresh>{VELOCITY_FIRE_THRESH}",
                    (20, fh - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, (100, 100, 100), 1)

    cv2.imshow("Goku Beam", frame)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('d'):
        DEBUG = not DEBUG
        print(f"Debug {'ON' if DEBUG else 'OFF'}")

cap.release()
cv2.destroyAllWindows()