"""Tests for mouse interaction coverage in FrequencyTimeline."""

from unittest.mock import MagicMock
from textual.events import MouseScrollUp, MouseScrollDown, MouseMove, Leave
from tui.widgets.frequency_timeline import FrequencyTimeline
from textual.message import Message

class _SizedTimeline(FrequencyTimeline):
    def __init__(self, width: int = 120) -> None:
        super().__init__()
        self._mock_width = width
        self.messages = []

    @property
    def size(self):
        return MagicMock(width=self._mock_width, height=3)

    def post_message(self, message: Message) -> bool:
        self.messages.append(message)
        return True

def _timeline(width: int = 120) -> _SizedTimeline:
    return _SizedTimeline(width=width)

def test_on_mouse_scroll_up():
    tl = _timeline()

    # Scroll up (no ctrl) -> ScrollRequest direction=1
    event = MouseScrollUp(x=0, y=0, delta_x=0, delta_y=0, button=0, shift=False, meta=False, ctrl=False, widget=tl)
    tl.on_mouse_scroll_up(event)
    assert len(tl.messages) == 1
    assert isinstance(tl.messages[-1], FrequencyTimeline.ScrollRequest)
    assert tl.messages[-1].direction == 1

    # Scroll up (ctrl) -> ZoomRequest direction=-1
    event_ctrl = MouseScrollUp(x=0, y=0, delta_x=0, delta_y=0, button=0, shift=False, meta=False, ctrl=True, widget=tl)
    tl.on_mouse_scroll_up(event_ctrl)
    assert len(tl.messages) == 2
    assert isinstance(tl.messages[-1], FrequencyTimeline.ZoomRequest)
    assert tl.messages[-1].direction == -1

def test_on_mouse_scroll_down():
    tl = _timeline()

    # Scroll down (no ctrl) -> ScrollRequest direction=-1
    event = MouseScrollDown(x=0, y=0, delta_x=0, delta_y=0, button=0, shift=False, meta=False, ctrl=False, widget=tl)
    tl.on_mouse_scroll_down(event)
    assert len(tl.messages) == 1
    assert isinstance(tl.messages[-1], FrequencyTimeline.ScrollRequest)
    assert tl.messages[-1].direction == -1

    # Scroll down (ctrl) -> ZoomRequest direction=1
    event_ctrl = MouseScrollDown(x=0, y=0, delta_x=0, delta_y=0, button=0, shift=False, meta=False, ctrl=True, widget=tl)
    tl.on_mouse_scroll_down(event_ctrl)
    assert len(tl.messages) == 2
    assert isinstance(tl.messages[-1], FrequencyTimeline.ZoomRequest)
    assert tl.messages[-1].direction == 1

def test_on_mouse_move():
    tl = _timeline()
    tl.hover_col = None

    # Set a starting state
    tl._last_hover_refresh = 0.0

    event = MouseMove(x=15, y=1, delta_x=0, delta_y=0, button=0, shift=False, meta=False, ctrl=False, widget=tl)
    tl.on_mouse_move(event)
    assert tl.hover_col == 15

def test_on_mouse_leave():
    tl = _timeline()
    tl.hover_col = 15

    event = Leave(node=tl)
    tl.on_mouse_leave(event)
    assert tl.hover_col is None
