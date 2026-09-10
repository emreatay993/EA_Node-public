"""PyQt6 meta-object registration guarantees for plain-Python bridge mixins.

The graph-canvas decomposition campaign splits GraphCanvasCommandBridge and
GraphCanvasStateBridge into per-domain plain-Python mixin modules composed
with QObject. That only works if pyqtSlot / pyqtProperty / pyqtSignal members
declared on a non-QObject mixin register in the composed class's QMetaObject
exactly like members declared on the QObject subclass itself.

This test pins that guarantee permanently, covering the exact shapes the real
bridges use:

- a bare pyqtSignal declared on the mixin
- a pyqtProperty with a notify signal (and setter) declared on the mixin
- single-decorated pyqtSlot with a result type
- a double-decorated overload slot (the existing
  GraphCanvasCommandBridge.upsert_node_link pattern)
- two mixins composed together (MRO stacking, as the ops packages will do)

If this test ever fails on a PyQt upgrade, the campaign fallback is to keep
the affected slot on the composition root as a one-line delegate to the ops
module (plan risk #3).
"""

from __future__ import annotations

import unittest

from PyQt6.QtCore import (
    Q_ARG,
    Q_RETURN_ARG,
    QMetaMethod,
    QMetaObject,
    QObject,
    Qt,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)


class _ExecutionFactsMixin:
    """Plain-Python mixin: signal + property/notify pair + overloaded slot."""

    counter_changed = pyqtSignal()
    payload_emitted = pyqtSignal(str)

    def _init_execution_facts(self) -> None:
        self._counter = 0

    @pyqtProperty(int, notify=counter_changed)
    def counter(self) -> int:
        return self._counter

    @counter.setter
    def counter(self, value: int) -> None:
        value = int(value)
        if value == self._counter:
            return
        self._counter = value
        self.counter_changed.emit()

    @pyqtSlot(str, result=str)
    @pyqtSlot(str, str, result=str)
    def render_label(self, prefix: str, suffix: str = "") -> str:
        return f"{prefix}|{suffix}" if suffix else f"{prefix}|<default>"

    @pyqtSlot(int, result=int)
    def bump_counter(self, delta: int) -> int:
        self.counter = self._counter + int(delta)
        return self._counter


class _CommandOpsMixin:
    """Second plain-Python mixin to prove MRO stacking registers too."""

    @pyqtSlot(result=bool)
    def command_ping(self) -> bool:
        return True


class _ComposedBridge(_ExecutionFactsMixin, _CommandOpsMixin, QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._init_execution_facts()


def _method_signatures(cls: type[QObject], method_type: QMetaMethod.MethodType) -> set[str]:
    meta = cls.staticMetaObject
    return {
        bytes(meta.method(index).methodSignature()).decode("utf-8")
        for index in range(meta.methodCount())
        if meta.method(index).methodType() == method_type
    }


class BridgeMixinMetaRegistrationTests(unittest.TestCase):
    def test_mixin_signals_register_in_meta_object(self) -> None:
        signals = _method_signatures(_ComposedBridge, QMetaMethod.MethodType.Signal)
        self.assertIn("counter_changed()", signals)
        self.assertIn("payload_emitted(QString)", signals)

    def test_mixin_slots_register_including_double_decorated_overloads(self) -> None:
        slots = _method_signatures(_ComposedBridge, QMetaMethod.MethodType.Slot)
        self.assertIn("render_label(QString)", slots)
        self.assertIn("render_label(QString,QString)", slots)
        self.assertIn("bump_counter(int)", slots)
        self.assertIn("command_ping()", slots)

    def test_mixin_property_registers_with_notify_signal(self) -> None:
        meta = _ComposedBridge.staticMetaObject
        index = meta.indexOfProperty("counter")
        self.assertGreaterEqual(index, 0, "mixin pyqtProperty missing from QMetaObject")
        prop = meta.property(index)
        self.assertEqual(prop.typeName(), "int")
        self.assertTrue(prop.hasNotifySignal())
        notify = bytes(prop.notifySignal().methodSignature()).decode("utf-8")
        self.assertEqual(notify, "counter_changed()")

    def test_mixin_members_are_callable_and_connectable_at_runtime(self) -> None:
        bridge = _ComposedBridge()
        notify_hits: list[int] = []
        payloads: list[str] = []
        bridge.counter_changed.connect(lambda: notify_hits.append(bridge.counter))
        bridge.payload_emitted.connect(payloads.append)

        self.assertEqual(bridge.bump_counter(3), 3)
        self.assertEqual(bridge.property("counter"), 3)
        self.assertEqual(notify_hits, [3])

        bridge.payload_emitted.emit("hello")
        self.assertEqual(payloads, ["hello"])
        self.assertTrue(bridge.command_ping())

    def test_overloaded_slot_dispatches_through_qmetaobject_invoke(self) -> None:
        bridge = _ComposedBridge()
        one_arg = QMetaObject.invokeMethod(
            bridge,
            "render_label",
            Qt.ConnectionType.DirectConnection,
            Q_RETURN_ARG(str),
            Q_ARG(str, "a"),
        )
        self.assertEqual(one_arg, "a|<default>")
        two_args = QMetaObject.invokeMethod(
            bridge,
            "render_label",
            Qt.ConnectionType.DirectConnection,
            Q_RETURN_ARG(str),
            Q_ARG(str, "a"),
            Q_ARG(str, "b"),
        )
        self.assertEqual(two_args, "a|b")

    def test_property_write_through_meta_object(self) -> None:
        bridge = _ComposedBridge()
        self.assertTrue(bridge.setProperty("counter", 11))
        self.assertEqual(bridge.counter, 11)


if __name__ == "__main__":
    unittest.main()
