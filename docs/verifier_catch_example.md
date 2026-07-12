# Verifier catching a bad claim — real run, not staged

Run `7e1cad662418`, `--provider anthropic`, against the bundled sample dataset,
inside Docker (`docker compose run --rm backend python -m src.demo_cli --provider anthropic`).
No tampering — this is what the verifier caught on an ordinary run.

## What the writer drafted

The executive summary's last sentence:

> Customer acquisition remains healthy at 650 customers per month [F4],
> positioning the organization for continued growth with targeted
> operational improvements.

`[F4]` was the finding for the task *"Analyze customer acquisition trend by
counting signups per month from customers.signup_date"* — but the analyst's
actual finding value was just `650`, the **total** customer count, not a
per-month figure. The writer's number is real (it traces to a real citation,
and the structural footnote check passed), but the sentence around it claims
something the finding doesn't support.

## What the verifier said

```
[F1] FAIL - The finding measures a single calculated value (48106.31), not explicitly a
     'monthly' metric. The sentence claims 'monthly revenue' but the finding doesn't
     confirm this is an average, a specific month, or recurring monthly figure. The
     phrase 'reflecting steady commercial traction' implies a trend that a single value
     cannot support.
[F4] FAIL - The finding value is 650 customers total, but the question asks to 'count
     signups per month.' Without confirmation that this is an average or recurring
     monthly figure vs. a single month's count, describing it as 'per month' or
     'monthly' may misrepresent the metric.

removed [F1]: (same reason as above)
removed [F4]: (same reason as above)
```

Both failures are the semantic check, not the mechanical one — the numbers
(`48106.31`, `650`) are exactly what their queries produce; the verifier's
recompute confirmed that. What it caught is a labeling problem: a single
aggregate value being described as if it were a recurring monthly rate. That
distinction is the entire reason the verifier runs two independent checks
instead of one (see `src/pipeline/verifier.py`) — a citation can be
numerically correct and still misrepresent what it measures.

## What shipped

The `[F1]`-citing sentence (in the "Revenue Performance" section) and the
`[F4]`-citing sentence (in the executive summary) were both stripped before
render. Full before/after and the rest of the run's stdout: `docker_run.log`
in this directory.

## A gap this surfaced (not fixed here)

The executive summary's first sentence is: *"...monthly revenue reaching
48106.31 USD and exceptional customer retention at 99.69% [F8]."* — two
numbers, one trailing footnote (`[F8]`, which is actually the retention
finding). The writer's structural check only requires a sentence to end
with *a* footnote, not that every number in it maps to *its own* citation,
so `48106.31` rode along uncited when `[F1]` (its real citation, used
elsewhere in the report) got redacted. The number happens to still be
correct here — the verifier's mechanical check would have caught it if not
— but the citation-attribution gap is real. Tightening the writer's check to
require one footnote per number, not per sentence, is the natural next fix.
