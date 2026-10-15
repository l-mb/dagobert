"""The comment lines of a ruamel.yaml round trip, which the edits of `store` keep where they belong.

ruamel.yaml hangs the comment lines after a value on its last scalar or flow collection, in a slot
of `node.ca.items[key]`: `[0]` after a list item, `[1]` the lines above the entry (one token per
line), `[2]` after a mapping value, `[3]` the lines above the first item of a list value.
`node.ca.comment[1]` holds the lines above the first item of a list, `node.ca.end` those at the
end of a block. A `Spot` names a slot by node and key."""

from __future__ import annotations

from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import CommentMark
from ruamel.yaml.tokens import CommentToken


def emptied(node: CommentedMap | CommentedSeq, key: str | int) -> None:
    """Make the list `node[key]` empty: `[]`, with every comment line that it held behind it."""
    rows = node[key]
    head = (rows.ca.comment or [None, None])[1] or []
    lines = _lines(head) + "".join(_above(rows, i) + _take(end(rows, i)) for i in range(len(rows)))
    node[key] = CommentedSeq()
    if entry := node.ca.items.get(key):
        entry[3] = None  # the lines above the first item, which ruamel.yaml keeps here too
    _put((node, key), lines)


def settle(node: Any) -> None:  # noqa: ANN401 ruamel nodes are untyped
    """Move the comment lines that ruamel.yaml keeps at the end of a block list or mapping (after
    flow rows) behind its last entry, where the edits look for them. The text stays the same."""
    if not isinstance(node, CommentedMap | CommentedSeq):
        return
    for value in node.values() if isinstance(node, CommentedMap) else node:
        settle(value)
    if node.ca.end and not node.fa.flow_style() and (spot := last(node)):
        _put(spot, _lines(node.ca.end))
        node.ca.end = []


Spot = tuple[CommentedMap | CommentedSeq, Any]  # a mapping or a list and one of its keys


def drop(node: Any, key: Any) -> None:  # noqa: ANN401 ruamel nodes are untyped
    """Delete the entry `key` of a mapping or a list. The comment lines around it stay where they
    are: behind the entry before it, or above the first item of a list. They belong to what
    follows. An end of line comment goes with the entry. After a flow collection ruamel.yaml keeps
    the lines above the next entry on that entry (`_above`)."""
    if isinstance(node, CommentedMap | CommentedSeq):
        keys = list(node) if isinstance(node, CommentedMap) else list(range(len(node)))
        at, lines = keys.index(key), _above(node, key) + _take(end(node, key))
        if at:
            _put(end(node, keys[at - 1]), lines)
        elif isinstance(node, CommentedSeq) and len(node) > 1:
            _head(node, lines)
        node.ca.items.pop(key, None)
    del node[key]


def end(node: CommentedMap | CommentedSeq, key: Any) -> Spot:  # noqa: ANN401
    """Where ruamel.yaml hangs the comment lines after the entry `key`: on the entry when its value
    is a scalar or a flow collection, else on the last entry below it."""
    value = node[key]
    block = isinstance(value, CommentedMap | CommentedSeq) and not value.fa.flow_style()
    return (last(value) if block else None) or (node, key)


def last(node: Any) -> Spot | None:  # noqa: ANN401 ruamel nodes are untyped
    """`end` of the last entry of `node`: the comment lines after `node` hang there. None for an
    empty node and a plain dict."""
    if not isinstance(node, CommentedMap | CommentedSeq) or not node:
        return None
    return end(node, next(reversed(node)) if isinstance(node, CommentedMap) else len(node) - 1)


def move_comment(source: Spot | None, target: Spot | None) -> None:
    """Move the comment lines after the value of `source` behind the value of `target`."""
    if source and target and (target[0] is not source[0] or target[1] != source[1]):
        _put(target, _take(source))


def _take(spot: Spot) -> str:
    """Remove the comment lines after the value at `spot` and return them. An end of line comment
    stays with its key."""
    entry = spot[0].ca.items.get(spot[1])
    if not entry or (token := entry[_slot(spot)]) is None:
        return ""
    comment, _, lines = str(token.value).partition("\n")
    if lines and comment:
        token.value = comment + "\n"
    elif lines:
        entry[_slot(spot)] = None
    return lines


def _above(node: CommentedMap | CommentedSeq, key: Any) -> str:  # noqa: ANN401
    """The comment lines that ruamel.yaml keeps before the entry `key`, one token per line."""
    return _lines((node.ca.items.get(key) or [None, None])[1] or [])


def _lines(tokens: list[CommentToken]) -> str:
    """Comment lines kept one token per line, the indent in the column of each."""
    return "".join(" " * token.start_mark.column + token.value for token in tokens)


def _put(spot: Spot, lines: str) -> None:
    """Add comment lines after the value at `spot`."""
    if not lines:
        return
    entry = spot[0].ca.items.setdefault(spot[1], [None, None, None, None])
    if entry[_slot(spot)] is None:
        entry[_slot(spot)] = CommentToken("\n" + lines, CommentMark(0))
    else:
        entry[_slot(spot)].value += lines


def _head(node: CommentedSeq, lines: str) -> None:
    """Add comment lines above the first item of `node`."""
    if not lines:
        return
    comment: list[Any] = node.ca.comment or [None, None]  # end of line comment, lines above
    node.ca.comment = comment
    if comment[1]:
        comment[1][-1].value += lines
    else:
        text = lines.lstrip(" ")
        comment[1] = [CommentToken(text, CommentMark(len(lines) - len(text)))]


def _slot(spot: Spot) -> int:
    """Where ruamel.yaml keeps the comment after a value: of a list item first, of a mapping
    value third."""
    return 0 if isinstance(spot[0], CommentedSeq) else 2
