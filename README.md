# Efficient Estimation of Bid-Ask Spreads from Open, High, Low, and Close Prices

> **Reference implementation (oracle for our tests):** https://github.com/eguidotti/bidask

---

   You can measure the effective spread directly if you have the trades and quotes. Most of the time you do not—you have daily open, high, low, and close, and that is all. The estimators that recover spreads from those four numbers (Roll, Corwin-Schultz, Abdi-Ranaldo) are biased downward when trading is infrequent, which is exactly the case where you most want them. This paper derives estimators that account for discretely observed prices and combines them optimally “to minimize estimation variance,” producing the EDGE estimator now shipping in the bidask package.

What makes this a good course project is the validation structure. The estimator has a published reference implementation, and the quantity it estimates has an observable ground truth in TAQ. You are not comparing your output to a printed table, you are comparing it to the thing itself.

Tasks:

Build the price and benchmark panel: CRSP daily open/high/low/close for the sample, plus TAQ effective spreads for the same stock-months as ground truth, with a summary table and a coverage figure (this is the data-cleaning deliverable)

Replicate the Monte Carlo: bias and RMSE of EDGE against Roll, Corwin-Schultz, and Abdi-Ranaldo as trading frequency falls

Replicate the empirical comparison: each estimator’s correlation with TAQ effective spreads, by size decile and through time

Implement the estimator from the paper’s equations, then test your implementation against the bidask package output—the package is the oracle, your code is what is being tested

Extend to futures: apply the estimators to E-mini and Treasury futures from Databento, where the true spread is observable from the top of book at essentially no data cost

Data sources: CRSP daily stock file and daily TAQ (WRDS); Databento GLBX (mbp-1) for the futures extension; reference implementation at eguidotti/bidask

Notes:

Do not call the package and stop. The deliverable is your own implementation plus the test suite that proves it matches.

The futures extension is the most interesting part and is not in the paper. Futures give you a clean, cheap ground truth in an asset class where the daily-data estimators are used constantly and validated rarely.

Citation: Ardia, David, Emanuele Guidotti, and Tim A. Kroencke. “Efficient estimation of bid-ask spreads from open, high, low, and close prices.” Journal of Financial Economics 161 (2024): 103916. https://doi.org/10.1016/j.jfineco.2024.103916 (working paper: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3892335)
