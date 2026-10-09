A limitation in the intended retaining wall costing is recorded as **L-34**,
before the code that would carry it is written.

Repair cost and undepreciated value are both meant to come off the **same**
square-metre rate, the only difference between them being the site multiplier.
One consequence of that is welcome and holds by construction: the multiplier is
never negative, so repair cost can never come out below UDV, which is the
direction Chris Ewens said the two run. That is a useful check rather than a
result.

But one rate for both assumes **the replacement wall is the same specification
as the one that failed**, and in practice a failed wall is often replaced with
something more substantial, built to a current design standard rather than the
one it was built to. If so, the replacement should be priced off a higher rate
than the UDV, and the two should not share one. Separately, NHC do not derive
UDV from these rates at all — Chris described a sheet of set fees, with the Act
rigid about what is allowable — so the same-rate approach is a stand-in for that
sheet as well.

**The bias has a known direction.** Settlement is `min(repair, cap)` less the
excess, so understating repair cost can only lower a settlement or leave it at
the cap. Pricing a replacement at the old wall's specification therefore
under-reports NHC's liability and never over-reports it. How far is not known,
and answering it needs the set fees and a view on what walls are typically
rebuilt to.

Recorded in `landloss.loss.pricing`, in `asset-pricing-approach.md` section 3.1
and in the module status. No code changed.
