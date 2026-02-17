# hint_tracker.py
_shown_keyboard_hint = set()

def reset_keyboard_hint():
    """Call this when reply buttons are updated to force hint again."""
    _shown_keyboard_hint.clear()