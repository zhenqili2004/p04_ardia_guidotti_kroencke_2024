# Project Specification

Course-level requirements, grading rubric, and reference examples for this
final project. All course text below is transcribed verbatim from the
instructor — keep this file in sync with any updates on the course page.

**Contents**

1. [Repository setup](#1-repository-setup)
2. [Final Project Instructions and Rubric](#2-final-project-instructions-and-rubric)
3. [Project Previews: What a Finished Project Looks Like](#3-project-previews-what-a-finished-project-looks-like)

---

## 1. Repository setup

Your project repository. Create a repository for your replication, scaffolded
from the chartbook cookiecutter template:

```bash
cruft create https://github.com/backofficedev/cookiecutter_chartbook
```

Name it **`p04_ardia_guidotti_kroencke_2024`** — the project number, then the
authors' last names, then the publication year. This repo is where all of your
work lives, and you'll publish your results as a ChartBook site on GitHub Pages.

If you keep the repo private, add **`jmbejara`** as a collaborator.

---

## 2. Final Project Instructions and Rubric

In this project, you'll replicate tables, figures, or data series from a well
known finance paper using the principles of reproducible analytical pipelines
(RAPs) learned in this class. Your replication must be automated from
end-to-end, formatted using the cookiecutter chartbook template. To create a
new project, use cruft: `cruft create https://github.com/backofficedev/cookiecutter_chartbook`.
See *Project Structure: "Chartbook" Template* for more details.

The final project is more than a replication — it is a product. You replicate
the core exhibits of your assigned paper, bring them up to the present, and
then build something on top of them that other people would actually want to
use. A central part of the project is making the case for that product: who
would clone your repository and run your code, and why.

### How the Project Runs

**Consultation (weeks 4 through 7).** A 1-on-1 meeting with the instructor,
booked through Microsoft Bookings. The consultation is ungraded. It is a
low-stakes chance to get feedback on your plan, and you leave it with an agreed
extension (see *The Extension Agreement* below).

**Submission (24 hours before your final project presentation).** Before we
meet, I will clone your repository, run it on my own machine, and read your
report and your project site. I grade the commit on your `main` branch as it
stood 24 hours before your meeting. Anything pushed after that is not graded.
Your project must run from a clean clone by following your README alone.
Reproducing your results without your help is the whole point of the course.

**Final project presentation (week 10, no later than Friday, December 11).**
A 30-minute meeting with your whole group, booked at the same link. You do not
present slides or give a demo: I will already have run your code. The whole
meeting is spent questioning each member individually, with questions written
from your repository and report (see *The Final Project Presentation* below).

### Receiving Your Assigned Project

You will be assigned a project from the list found [here](#).

Your preference will be taken into account when assigning the projects. You can
rank your preferred projects using a Google Form: **TBD** (the link will be
posted on Canvas). Please, only submit one response per group. Your group must
have exactly 4 people in it. Students can not choose to work alone, and a group
of any other size requires my permission in advance. I will use your responses
to assign each group a project.

### The Extension Agreement

Come to the consultation with a **one-page pitch** that answers five questions:

1. What does the paper claim? Say it in one sentence.
2. What does the paper *not* do that someone would want?
3. What will you build?
4. Who would clone it, and what would they do with it?
5. How will we know it worked?

Also say what your **data validation** will check (see the rubric below).

We agree on the extension in the meeting. Afterward, add an **Extension**
section to your README that records what we agreed. That README section is what
your extension is graded against. If your plan changes substantially later,
check with me first.

For an example of an extension pitched this way, see *Project Previews*
(§3 below).

### Update Versus Extension

These are graded separately.

The **update** recomputes the paper's exhibits with data through the most
recent date available, and says in a sentence or two whether the paper's result
held up after publication. Once the pipeline works, the update should be close
to mechanical. That is a sign the pipeline is built well, but it is *not* the
extension.

The **extension** adds something the paper does not have. Examples of what can
count:

- An out-of-sample or regime test that the paper could not run (did the effect
  survive decimalization, zero commissions, or the 2022 rate hikes?)
- A cleaned, documented dataset that others in the field would use, with the
  code that keeps it current
- A signal or monitor that updates on fresh data, such as a daily series or a
  dashboard
- A head-to-head comparison against a competing measure on the same sample
- The paper's method applied to a new market, asset class, or frequency
- A conceptual gap in the paper's reasoning, with a measurement that addresses
  it

On their own, these **do not** count: extending the sample (that is the
update), restyled versions of the paper's exhibits, or summary statistics of
the data you already replicated.

### The Final Project Presentation

Each member of the group is questioned individually, for about seven minutes
each. Questions may or may not come from parts of the project you wrote. If
your name is on the project, you are expected to understand every part of it,
not only the parts you wrote. Expect questions of these kinds:

- **The paper**: what it claims, why it matters, and the economics behind the
  main result.
- **The data**: where each source comes from, what each filter does and why it
  is there, and what would break without it.
- **Design choices**: why the pipeline is organized the way it is, how you
  chose your test tolerances, and what you would change.
- **The extension**: why someone would use it, where it stops being reliable,
  and what you would build next.
- **Working with the code**: for example, "If I changed `END_DATE`, what
  reruns, and how does `doit` know?"

Treat it like a job interview where this project is on your resume. An
interviewer won't ask you to recite the paper. They will ask what you built,
why you built it that way, and whether you can tell them something useful they
didn't already know. Answer like that. *Project Previews* (§3 below) has
example questions for three past projects.

### Final Project Grading Rubric

**Total: 200 points.** Each item is prorated by its degree of completion. For
example, if you replicate 50% of the numbers from a table, you'll get 50% of
the points for that table. Some adjustments may be made by discretion based on
the difficulty of the task.

#### Group items (115 points)

**20/20 — Replication.** Replicate the series, tables, and/or figures listed
for your assigned project. Choose a reasonable tolerance and construct unit
tests to ensure that your numbers match the paper's within this tolerance. **Fix
the tolerance before you see your results, not after.**

**10/10 — Update.** Recompute the same series, tables, and/or figures with data
up until the present (or at least the most recently available data), and state
whether the paper's result held up.

**10/10 — Data validation.** Check the data itself, not just the code: unit
tests check your code against inputs you built, and validation checks your data
against something you know independently (see *Data Validation*). For example:

- your series reconciles with a second source (CRSP market cap against the S&P
  500 index level, your TAQ volume against CRSP daily volume, or your measure
  against a series the authors post)
- an identity the data must satisfy holds (put–call parity, or portfolio
  weights that sum to one)
- each filter removes about as many observations as you expect
- coverage through time has no unexplained breaks

These checks run as tests in the pipeline, each with a tolerance fixed before
you see the results. Then build at least one table and one figure of your own
that show what those checks found, such as the reconciliation against the
second source, the filter-by-filter observation counts, or coverage through
time. **Each caption says what the check found and what it means for trusting
your results.**

**30/30 — Extension.** Did you deliver the extension agreed at the consultation
and recorded in your README? Is it useful for a reason you can state? Is it
tested and documented?

**9/9 — Report and published site.**

- **(5)** A single LaTeX document that briefly describes the project and
  contains all the tables and charts your code produces. Give a high-level
  overview of how the project went: where you found success, where the
  challenges were, and which data sources you used. It should not contain code
  snippets. Every table and figure needs a caption that tells me what I should
  learn or take away from it.
- **(4)** A ChartBook site, built by the pipeline and published on GitHub
  Pages, with the project's dataframes and charts registered in
  `chartbook.toml` and each dataframe's sources recorded, so a reader can
  follow the data from the raw pulls to the final tables (see the published
  site on *Project Previews*). The site includes at least one Jupyter notebook
  that gives a brief tour of the cleaned data and of the analysis performed in
  the code. Code snippets are welcome in the notebook. It should look something
  like one of the HW guides we used, e.g. *HW 1 Guide D: Constructing the
  Fama–French Factors*.

**36/36 — Engineering standards.**

- **(8)** The project runs end to end with PyDoit from a clean clone on my
  machine, following only your README.
- **(4)** Data cleaning lives in its own file or files, whose only purpose is
  to put the data into a tidy format. The analysis is kept in separate files.
- **(4)** Every statistic in the LaTeX document is generated automatically by
  the code.
- **(4)** Tests, both unit tests and validation, are well motivated, each has a
  purpose, and none are unnecessary or repetitive. A **GitHub Actions**
  workflow runs the tests on every push and pull request. Tests that need WRDS
  or other credentials may be skipped in CI, but the rest must run there, on
  small samples if needed, and pass.
- **(4)** The repository and its entire Git history are free of copyrighted
  material (e.g., raw data), secrets such as API keys, and any trace of a
  `.env` file.
- **(4)** Configuration separates secrets and machine facts from the analysis.
  `.env` holds the API keys, the WRDS username, and the data directory, with
  reasonable defaults in `settings.py` and the required variables described in
  a `.env.example` file. The `START_DATE` and `END_DATE` of the analysis are
  committed constants in `settings.py`, **never read from `.env`**: two people
  with different `.env` files who build the same commit must get the same
  bytes.
- **(4)** The project was scaffolded from the cookiecutter chartbook template
  with `cruft create https://github.com/backofficedev/cookiecutter_chartbook`,
  the README describes the project and gives clear instructions for running it
  end to end (environment setup and `doit`), and a `requirements.txt` file
  lists the required packages.
- **(4)** Each Python file has a docstring at the top that describes what the
  file does, and each function has a reasonably descriptive name and, when
  appropriate, a docstring. (No need to go overboard, but the code should be
  reasonably clean.)

#### Individual items (85 points)

**35/35 — Individual contribution.** Did I contribute a substantial part of
the code? I look at the commit history and at pull requests: who authored
them, who reviewed them, and who merged them. **Every pull request must be
reviewed by another member of the group before it is merged**, and every
member must have **authored at least one pull request that was merged** and
**reviewed at least one written by a teammate**.

**50/50 — Final project presentation.** Graded individually from your answers
in the 30-minute meeting, as described in *The Final Project Presentation*
above.

---

## 3. Project Previews: What a Finished Project Looks Like

Every final project asks you to do the same thing: take a finance paper,
rebuild its dataset from the original sources, reproduce the tables and figures
that carry its main result, and ship the whole thing as something another
person can clone and run. That description stays abstract until you see what a
finished one looks like.

So this page does not show you figures clipped out of published papers. It
shows you three projects that students in this course actually built, one for
each of three things a good project gets right: the published site, the
written report, and the extension. Each section says what to look at and why
it is worth copying, and ends with questions like the ones you will be asked
at your final project presentation.

---

### 3.1. The published site

**Jie Lin and Zimeng Yi — Golez and Jackwerth (2024), *Holding Period Effects
in Dividend Strip Returns*.** Their project recovers dividend strip prices
from S&P 500 index option quotes and measures how strip returns depend on the
holding period.

- Paper
- Project site

Open it and look at the sidebar before you read anything. It has two sections,
**Pipeline Charts** and **Pipeline Dataframes**, and the second one is the
pipeline itself. Eighteen registered dataframes, each with its own page, and
each page records which dataframes it was built from:

```
optionmetrics_spx_monthly, crsp_sp500_daily   ->  clean_options
clean_options                                 ->  implied_rates  ->  implied_rates_1y
clean_options, implied_rates                  ->  strip_prices
clean_options, implied_rates                  ->  all_strip_prices
strip_prices, all_strip_prices,
  clean_crsp_sp500_monthly, fama_french_monthly,
  crsp_treasury_returns                       ->  monthly_returns
```

You can read the whole data lineage of the project off the navigation without
running a single line of code. The eight raw vendor pulls sit at the top with
no parents; `monthly_returns`, the table the paper's results come out of,
names all five of the inputs that feed it.

**What to look at:**

- **The naming tells you the stage.** Raw pulls keep the vendor's name
  (`optionmetrics_spx_raw`, `crsp_sp500_daily`, `fred_treasury_rates`).
  Cleaned versions are `clean_*`. Derived quantities are named for the thing
  they are, not the step that made them: `implied_rates`, `strip_prices`,
  `monthly_returns`. Someone who has never seen the project can find the right
  table on the first guess.
- **Provenance is recorded, not implied.** Open `clean_options` and the page
  says it was derived from `optionmetrics_spx_monthly` and `crsp_sp500_daily`.
  That is what turns a folder of parquet files into a catalog: not the files,
  the description of where each one came from.
- **Raw and cleaned are both registered.** Publishing only the finished tables
  would have been less work. Registering the raw pulls beside them is what
  lets a reader check the cleaning instead of trusting it.
- **The Chart List is indexed by category and tag**, so charts are findable by
  subject rather than by filename.

This is the standard to aim at for your own ChartBook site, and it is worth
opening on the day you start rather than the week you finish. Deciding what to
register, and what to call it, gets much harder to change later.

**Questions you might be asked:**

- The paper insists on option-implied interest rates rather than the zero
  curve. Why does that matter for strip prices, and what would Figure 1 look
  like if you had used Treasury rates?
- Which option quotes do you need to back out a strip price? Which
  OptionMetrics filters did you apply, and why?
- Why should the volatility of strip returns depend on the holding period?
- If I tighten a filter in `clean_options`, which of your eighteen dataframes
  are rebuilt, and how does `doit` know?
- A portfolio manager asks whether short-maturity dividend strips are worth
  trading. What does your data tell them?

---

### 3.2. The written report

**Anthony Mazy and Stefano Ramponi — Lewellen (2004), *Predicting Returns with
Financial Ratios*.** Thirteen pages, fifteen numbered exhibits, every
statistic generated by the code.

- Paper
- Repository

The report is built from `reports/replication_report.tex`. What makes it
worth studying is not the prose, it is the machinery behind the numbers, and
that machinery is all in the repository:

- **`src/paper_values.py`** holds the paper's published numbers, transcribed
  by hand from the PDF. The module is deliberately data-only and imports
  nothing from the pipeline, "so it can be read as a standalone reference and
  diffed against the PDF." It opens with a block headed
  `TRANSCRIPTION HAZARD -- read before editing`. Transcribing a table wrong
  is the quietest way for a replication to go wrong, and they treated that
  risk as a first-class part of the design.
- **`tests/test_replication_vs_paper.py`** parameterizes one test per
  `(predictor, window)` cell, so a single number missing produces a single
  named failure instead of one opaque red mark. Two of the paper's tables rest
  on a firm screen the paper never specifies, so those cells cannot be pinned
  exactly; the suite records that reason and the expected outcome rather than
  widening the tolerance to paper over it. Their comment explaining why is
  the best single sentence about testing in any project on this page:

  > Loosening tolerances until these passed would make the whole suite
  > meaningless — a tolerance is only worth anything if it was fixed before
  > the numbers were seen.

  Write the paper's numbers down first, in their own file, before you have
  computed yours. Then the suite can tell you something.

- **`src/diagnose_bm.py`** is a standalone diagnostic that traces an outlier
  B/M or E/P statistic back to the exact month and fiscal-year data that
  produced it, written, in its own words, so they could stop "guessing at
  fixes blind." It is the difference between knowing a number is off and
  knowing why.
- **`src/public_fallback.py`** lets parts of the project run without WRDS
  credentials, so a reader who has no subscription can still get somewhere.
  Almost nobody thinks to do this, and it is the single thing that most
  widens the audience for a replication.

**The lesson.** Your replication will not match everything, and that is
normal — it happens to professional replicators on every paper. What earns
the points is that you noticed, that the report says so, and that the
repository holds the evidence.

**Questions you might be asked:**

- Explain Stambaugh bias in two sentences. Why is the bias upward?
- What does conditioning on ρ < 1 buy you? Your own exhibit says
  dividend-yield persistence has eroded since the paper was written. What
  does that do to the estimator today?
- Two of the paper's tables rest on a firm screen the paper never specifies.
  How did you set the tolerance for those cells, and why not loosen it?
- Walk me through building book-to-market from Compustat and CRSP. Where
  could look-ahead bias creep in?
- A colleague shows you a predictive regression with a t-statistic of 3 on a
  highly persistent predictor. What do you ask them?

---

### 3.3. The extension

**Riley Haas and Marija Jovicic — Martin and Shi, *Forecasting Crashes with
a Smile*.** In their cohort, each group pitched its plan to the class. Theirs
scored 19.5 out of 20, and four classmates asked to be put in touch about
the code afterward, which is the outcome an extension is really aiming at.

- Paper
- Repository

This paper is the basis of HW 3, so the replication half will be familiar to
you by the time you see this. Study their extension.

**What their plan did:**

- **It found a gap in the paper's reasoning, not in its data.** The paper
  bounds the crash probability of an individual stock. Riley and Marija
  pointed out that the average of individual crash probabilities is not the
  probability of a sector crash, because idiosyncratic volatility diversifies
  away in a portfolio. That is a conceptual objection, and it is the kind of
  idea a data hunt does not produce.
- **It proposed a direct measurement, not a workaround.** Rather than
  aggregating single-name bounds, measure sector crash probability straight
  from the option surfaces of sector ETFs.
- **It named the product concretely.** An installable `crashbounds` package,
  plus a three-level case study on the failure of Silicon Valley Bank. Not
  "a cleaned dataset" in the abstract — a thing with a name that somebody
  could `pip install`.
- **It told the class who would use it, and the class believed it.** The four
  follow-up requests were the proof.

**The structure to steal, for your consultation and for your final project
presentation.** State the paper's claim in one sentence. Name the specific
thing the paper does not do. Say what you will build. Say who would clone it
and why. Then defend all four when asked.

**Questions you might be asked:**

- In words, what does the paper's bound bound, and what information from the
  option market does it use?
- Why is the average of single-stock crash probabilities not the probability
  of a sector crash?
- What did your bounds say about Silicon Valley Bank before March 2023? How
  would you tell a real signal from a false alarm?
- Who would `pip install crashbounds`, and what would they need from you
  before relying on it every day?
- How would you validate a crash-probability signal out of sample?

---

### One thing to keep in mind

All three of these were built by groups of two. Yours has four, so aim past
them: a more complete replication, tests that cover more of it, and an
extension with more in it. The rubric asks the same things of you that it
asked of them, and you have twice the hands.

For the full set of finished projects from the last four cohorts, with
repositories and sites, see **Past Final Projects**.
