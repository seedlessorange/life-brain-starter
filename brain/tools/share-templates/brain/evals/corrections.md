# Draft eval: her corrections as test cases

Each heading is one lesson from the "Learned from corrections" section of
writing-rules.md, turned into a test. `drafteval.py` sends the Before text
through the same revise call the page uses, with a plain ask that does not
name the mistake, then checks whether the mistake survived. A lesson that
keeps failing needs stronger wording in the rules; one that always holds can
be folded in.

How to add a case (Claude does this in the same session as the Learned
entry): a `## short-name` heading, then the fields, then the Before text as a
quote. Use the real draft when it exists. Fields:

- **Lesson:** the rule, one or two sentences. The judge reads this.
- **Kind / To / Task:** what the draft was, as its front matter would say.
- **From:** where the lesson came from, and whether the text is the real
  draft or rebuilt around her quoted lines.
- **Gone:** exact phrases that must not survive, separated by `|`.
- **Keep:** facts that must survive the rewrite, separated by `|`.
- **Her fix:** what she changed it to, when she said.
- **Ask:** the revise instruction, when "Get this ready to send." is wrong.
