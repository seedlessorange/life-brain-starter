"""The page's questions: at most three a day, one tap each (8 Oct audit).

model.asks() decides what to ask and marks a guess only when it has a
reason on disk; serve.py ask_answer() does what the answer says. This file
only draws them, each as its own line in For you, like the questions in
questions.md: the question on the line, the reason and the buttons one
click down.
"""
import model as M
from build import _tid, e, tray_item


def _title(q):
    """The line in For you, worded as the question it is."""
    if q["kind"] == "finished":
        return q["ws"] + ": finished?", ""
    if q["kind"] == "pile":
        return q["text"], ""
    if q["kind"] == "late":
        return q["text"] + ": still on?", ""
    if q["src"] == "today.md":
        return q["text"] + ": did you talk?", ""
    return q["text"], "keeps slipping"


def ask_items(live, cfg=None):
    """For you lines, one per question, most useful first."""
    out = []
    for q in M.asks(live, cfg):
        title, sub = _title(q)
        btns = "".join(
            f'<button class="mini{" primary" if a == q["guess"] else ""}"'
            f' data-askact="{e(a)}"'
            + (' title="The brain&rsquo;s guess"' if a == q["guess"] else "")
            + f">{e(label)}</button>"
            for a, label in q["buttons"])
        items = "".join(f"<li>{e(x)}</li>" for x in q.get("items") or [])
        body = (f'<div class="pqrow needs-server" data-qid="{e(q["qid"])}">'
                f'<p class="pqwhy">{e(q["why"])}</p>'
                + (f'<ul class="pqlist">{items}</ul>' if items else "")
                + f'{btns}'
                '<span class="mshelp pq-help"></span></div>')
        out.append(tray_item(_tid("ask", q["qid"]), "answer", title, body,
                             sub=sub))
    return out
