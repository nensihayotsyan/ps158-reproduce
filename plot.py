"""Median net worth of families with children, by education of the reference person.

Reads only what get_data.py downloaded (data/manifest.json and data/*.dta).

Definitions (SCF summary extract variables):
    NETWORTH  family net worth, in the extract's constant dollars
    WGT       survey weight
    KIDS      number of children in the household; families with children: KIDS > 0
    EDCL      education of the reference person: 1 no high-school diploma,
              2 high-school diploma or GED, 3 some college, 4 bachelor's or more
              HS or less: EDCL in {1, 2};  BA or more: EDCL == 4
    Y1        case ID with the implicate number (1-5) as its last digit (X1 in 1989)

Weights: each family appears five times (five imputations). For each implicate
the weighted median is taken using WGT, and the five medians are averaged.

Output: figure.png and wealth_gap.csv
"""
import json
import re
import sys
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
GROUPS = {"BA or more": [4], "High school or less": [1, 2]}


def weighted_median(x, w):
    order = np.argsort(x)
    x, w = x[order], w[order]
    cum = np.cumsum(w)
    return x[np.searchsorted(cum, 0.5 * cum[-1])]


def dollar_year(manifest):
    years = set()
    for m in manifest.values():
        for s in m["dollar_base_text"]:
            years.update(re.findall(r"\b((?:19|20)\d\d) dollars", s))
    if len(years) != 1:
        sys.exit(f"Could not establish one common dollar base from the Fed pages: {years or 'none'}. "
                 "Check data/manifest.json before plotting.")
    return years.pop()


def main():
    manifest = json.loads((DATA / "manifest.json").read_text())
    base = dollar_year(manifest)

    rows = []
    for year, m in sorted(manifest.items()):
        df = pd.read_stata(DATA / m["file"], convert_categoricals=False)
        df.columns = df.columns.str.lower()
        df = df[df["kids"] > 0]
        df["implicate"] = df["y1" if "y1" in df else "x1"] % 10  # 1989 names it X1
        for label, codes in GROUPS.items():
            g = df[df["edcl"].isin(codes)]
            meds = [weighted_median(s["networth"].to_numpy(), s["wgt"].to_numpy())
                    for _, s in g.groupby("implicate")]
            rows.append({"year": int(year), "group": label, "median_networth": np.mean(meds),
                         "families_in_sample": len(g) // 5})

    out = pd.DataFrame(rows).pivot(index="year", columns="group", values="median_networth")
    out["ratio"] = out["BA or more"] / out["High school or less"]
    out.to_csv(HERE / "wealth_gap.csv")
    print(f"Median net worth, families with children ({base} dollars):")
    print(out.round(1).to_string())

    plt.rcParams.update({"font.family": "serif", "font.size": 9, "axes.linewidth": 0.6,
                         "xtick.major.width": 0.6, "ytick.major.width": 0.6})
    first, last = out.index.min(), out.index.max()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7, 5.0))
    styles = {"BA or more": dict(linestyle="-", marker="o", markerfacecolor="black"),
              "High school or less": dict(linestyle="--", marker="s", markerfacecolor="white")}
    for label, st in styles.items():
        a1.plot(out.index, out[label] / 1000, color="black", linewidth=1, markersize=4,
                label=label, **st)
    a1.set_ylabel(f"Thousands of {base} dollars")
    a1.set_title("(a) Median net worth", loc="left", fontsize=9)
    a1.legend(frameon=False, title="Reference person's education", title_fontsize=8, fontsize=8,
               loc="lower left", bbox_to_anchor=(0.0, 0.12), alignment="left")
    a2.plot(out.index, out["ratio"], color="black", linewidth=1, marker="o", markersize=4,
            markerfacecolor="black")
    a2.set_ylabel("BA or more / HS or less")
    a2.set_title("(b) Ratio of medians", loc="left", fontsize=9)
    a2.set_ylim(bottom=0)
    for a in (a1, a2):
        a.set_xticks(out.index)
        a.tick_params(axis="x", rotation=90, labelsize=8)
        a.spines[["top", "right"]].set_visible(False)
    caption = (f"Figure 1. Median net worth of U.S. families with children by the education of the "
               f"family's reference person, {first}\u2013{last}, in constant {base} dollars.")
    note = ("Source: Board of Governors of the Federal Reserve System, Survey of Consumer Finances, "
            f"summary extract public data, {first}\u2013{last}. Families with children are those with "
            "KIDS > 0; education is that of the reference person (EDCL). Medians are weighted with the survey weight (WGT), computed separately for "
            "each of the five implicates and averaged. Constant-dollar values as provided by the "
            "Federal Reserve in the historical summary extract files.")
    if any("github.com" in m["url"] for m in manifest.values()):
        note += " Files obtained from a public GitHub copy of the Federal Reserve's extracts."
    fig.subplots_adjust(left=0.09, right=0.98, top=0.93, bottom=0.4, wspace=0.3)
    fig.text(0.02, 0.235, textwrap.fill(caption, 92), fontsize=9, fontweight="bold", va="top")
    fig.text(0.02, 0.155, textwrap.fill(note, 125), fontsize=7, va="top", linespacing=1.3)
    fig.savefig(HERE / "figure.png", dpi=300)
    print(f"Saved {HERE / 'figure.png'}")


if __name__ == "__main__":
    main()
