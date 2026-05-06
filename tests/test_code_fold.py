"""FoldController: indent-based fold detection, nested folds, set_enabled."""
from src.viewer import CodeViewer


PY = """\
def outer():
    if True:
        print("nested")
        print("more")
    print("after if")

def other():
    return 1

x = 0
"""


def test_is_foldable_detects_header_lines(qapp):
    v = CodeViewer(); v.setPlainText(PY); v.fold.set_enabled(True)
    doc = v.document()
    assert v.fold.is_foldable(doc.findBlockByNumber(0))   # def outer():
    assert not v.fold.is_foldable(doc.findBlockByNumber(5))  # print("after if")
    assert v.fold.is_foldable(doc.findBlockByNumber(6))   # def other():
    assert not v.fold.is_foldable(doc.findBlockByNumber(9))  # x = 0


def test_fold_hides_children_only(qapp):
    v = CodeViewer(); v.setPlainText(PY); v.fold.set_enabled(True)
    doc = v.document()
    v.fold.toggle(doc.findBlockByNumber(0))
    hidden = [n for n in range(doc.blockCount())
              if not doc.findBlockByNumber(n).isVisible()]
    assert hidden == [1, 2, 3, 4, 5]


def test_unfold_restores_all_children(qapp):
    v = CodeViewer(); v.setPlainText(PY); v.fold.set_enabled(True)
    doc = v.document()
    v.fold.toggle(doc.findBlockByNumber(0))
    v.fold.toggle(doc.findBlockByNumber(0))
    hidden = [n for n in range(doc.blockCount())
              if not doc.findBlockByNumber(n).isVisible()]
    assert hidden == []


def test_nested_unfold_preserves_inner_fold(qapp):
    """Outer fold-then-unfold must keep an inner fold collapsed."""
    v = CodeViewer(); v.setPlainText(PY); v.fold.set_enabled(True)
    doc = v.document()
    v.fold.toggle(doc.findBlockByNumber(1))   # if True:
    v.fold.toggle(doc.findBlockByNumber(0))   # def outer():
    v.fold.toggle(doc.findBlockByNumber(0))   # unfold outer
    visible = [n for n in range(6) if doc.findBlockByNumber(n).isVisible()]
    assert visible == [0, 1, 4, 5]   # 2,3 still hidden by inner fold


def test_set_enabled_false_unfolds_everything(qapp):
    v = CodeViewer(); v.setPlainText(PY); v.fold.set_enabled(True)
    doc = v.document()
    v.fold.toggle(doc.findBlockByNumber(0))
    v.fold.set_enabled(False)
    hidden = [n for n in range(doc.blockCount())
              if not doc.findBlockByNumber(n).isVisible()]
    assert hidden == []
    assert not v.fold.enabled


def test_gutter_widens_when_folding_enabled(qapp):
    v = CodeViewer(); v.setPlainText(PY)
    base = v.line_number_area_width()
    v.fold.set_enabled(True)
    assert v.line_number_area_width() == base + v.fold.MARKER_W
