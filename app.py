import cv2
import time
import math
import pyautogui
import screen_brightness_control as sbc
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import mediapipe as mp

# HandPilot: Windows 11 hand-gesture control prototype
# Gestures are intentionally conservative. Keep your hand visible and well lit.

pyautogui.FAILSAFE = True  # move cursor to top-left corner to abort PyAutoGUI actions
pyautogui.PAUSE = 0.02

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

SCREEN_W, SCREEN_H = pyautogui.size()
CAM_W, CAM_H = 960, 540

def get_volume_interface():
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))

try:
    volume = get_volume_interface()
except Exception as e:
    volume = None
    print("Audio control unavailable:", e)

def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)

def finger_up(hand, tip, pip):
    return hand.landmark[tip].y < hand.landmark[pip].y

def is_finger_up(hand, tip, pip):
    return finger_up(hand, tip, pip)

def draw_text(img, text, y, color=(255, 255, 255)):
    cv2.putText(img, text, (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)

def main():
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
    if not cap.isOpened():
        print("Couldn't open webcam. Close apps that may be using it and try again.")
        return

    mode = "MOUSE"
    last_action = 0.0
    action_cooldown = 0.8
    smooth_x, smooth_y = SCREEN_W / 2, SCREEN_H / 2
    alpha = 0.28
    prev_scroll_y = None
    status = "Show one hand to camera"
    brightness_value = 60

    with mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        model_complexity=0,
        min_detection_confidence=0.65,
        min_tracking_confidence=0.6,
    ) as hands:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)
            now = time.time()
            gesture = "No hand"

            if result.multi_hand_landmarks:
                hand = result.multi_hand_landmarks[0]
                mp_draw.draw_landmarks(frame, hand, mp_hands.HAND_CONNECTIONS)
                lm = hand.landmark

                index_up = is_finger_up(hand, 8, 6)
                middle_up = is_finger_up(hand, 12, 10)
                ring_up = is_finger_up(hand, 16, 14)
                pinky_up = is_finger_up(hand, 20, 18)
                thumb_index = distance(lm[4], lm[8])

                # Open palm (four fingers up) toggles mode, protected by cooldown.
                if index_up and middle_up and ring_up and pinky_up and thumb_index > 0.08:
                    gesture = "OPEN PALM"
                    if now - last_action > action_cooldown:
                        mode = "VOLUME" if mode == "MOUSE" else "MOUSE"
                        status = f"Mode changed to {mode}"
                        last_action = now
                    prev_scroll_y = None

                elif mode == "MOUSE":
                    if index_up and not middle_up:
                        gesture = "INDEX = MOVE"
                        target_x = (1 - lm[8].x) * SCREEN_W
                        target_y = lm[8].y * SCREEN_H
                        smooth_x += (target_x - smooth_x) * alpha
                        smooth_y += (target_y - smooth_y) * alpha
                        pyautogui.moveTo(int(smooth_x), int(smooth_y), _pause=False)

                        # Pinch thumb + index for click.
                        if thumb_index < 0.045 and now - last_action > action_cooldown:
                            pyautogui.click()
                            status = "Left click"
                            last_action = now

                    elif index_up and middle_up and not ring_up:
                        gesture = "INDEX + MIDDLE = SCROLL"
                        y = lm[8].y
                        if prev_scroll_y is not None:
                            delta = prev_scroll_y - y
                            if abs(delta) > 0.012:
                                pyautogui.scroll(int(max(-5, min(5, delta * 90))))
                        prev_scroll_y = y
                    else:
                        prev_scroll_y = None

                elif mode == "VOLUME":
                    if index_up and middle_up and not ring_up and not pinky_up:
                        gesture = "TWO FINGERS = BRIGHTNESS"
                        target = int(max(10, min(100, (1 - lm[8].y) * 100)))
                        try:
                            sbc.set_brightness(target)
                            brightness_value = target
                            status = f"Brightness {target}%"
                        except Exception:
                            status = "Brightness control unsupported on this display"
                    elif index_up and not middle_up:
                        gesture = "INDEX HEIGHT = VOLUME"
                        if volume is not None:
                            level = float(max(0.0, min(1.0, 1 - lm[8].y)))
                            try:
                                volume.SetMasterVolumeLevelScalar(level, None)
                                status = f"Volume {int(level * 100)}%"
                            except Exception:
                                status = "Couldn't set volume"
                    elif not index_up and not middle_up and not ring_up and not pinky_up:
                        gesture = "FIST = MUTE"
                        if volume is not None and now - last_action > action_cooldown:
                            try:
                                muted = bool(volume.GetMute())
                                volume.SetMute(not muted, None)
                                status = "Muted" if not muted else "Unmuted"
                                last_action = now
                            except Exception:
                                status = "Couldn't toggle mute"

            draw_text(frame, f"HandPilot | Mode: {mode}", 28, (0, 255, 180))
            draw_text(frame, f"Gesture: {gesture}", 58)
            draw_text(frame, f"Status: {status}", 88)
            draw_text(frame, "Open palm: switch mode | Q: quit | Move cursor to top-left to abort", CAM_H - 18, (255, 220, 0))
            cv2.imshow("HandPilot - Gesture Control", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
