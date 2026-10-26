
import re
import unicodedata

import pandas as pd
import streamlit as st
from rapidfuzz import fuzz, process


# =====================================================
# PAGE CONFIGURATION
# =====================================================

st.set_page_config(
    page_title="NBA Production Value Dashboard",
    page_icon="🏀",
    layout="wide",
)

st.title("NBA Production Value Dashboard")


# =====================================================
# LOAD DATA
# =====================================================

@st.cache_data
def load_data():
    wins = pd.read_csv("productionvalue.csv")
    vorp = pd.read_csv("vorp.csv")

    wins.columns = wins.columns.str.strip()
    vorp.columns = vorp.columns.str.strip()

    required_wins = {"Team", "Player", "Wins Added"}
    required_vorp = {"Team", "Name", "Rating"}

    if not required_wins.issubset(wins.columns):
        raise ValueError(
            f"productionvalue.csv needs columns: {required_wins}"
        )

    if not required_vorp.issubset(vorp.columns):
        raise ValueError(
            f"vorp.csv needs columns: {required_vorp}"
        )

    for df, player_col in [(wins, "Player"), (vorp, "Name")]:
        df[player_col] = df[player_col].fillna("").astype(str).str.strip()
        df["Team"] = df["Team"].fillna("").astype(str).str.strip()

        df.drop(
            df[
                (df[player_col] == "")
                | (df["Team"] == "")
            ].index,
            inplace=True,
        )

    wins["Wins Added"] = pd.to_numeric(
        wins["Wins Added"], errors="coerce"
    )
    vorp["Rating"] = pd.to_numeric(
        vorp["Rating"], errors="coerce"
    )

    wins = wins.dropna(subset=["Wins Added"]).copy()
    vorp = vorp.dropna(subset=["Rating"]).copy()

    return wins, vorp


try:
    wins_df, vorp_df = load_data()
except Exception as error:
    st.error(f"Error loading data: {error}")
    st.stop()


# =====================================================
# NAME NORMALIZATION AND MATCHING
# =====================================================

def normalize_name(name):
    """Normalize capitalization, accents, punctuation, and spacing."""
    name = unicodedata.normalize("NFKD", str(name))
    name = "".join(
        c for c in name if not unicodedata.combining(c)
    )
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def normalize_team(team):
    return normalize_name(team)


wins_names = sorted(wins_df["Player"].unique())
vorp_names = sorted(vorp_df["Name"].unique())

# Canonical names allow one exclusion to affect both datasets.
# Wins Added names are preferred as canonical names.
name_map = {
    ("wins", name): name
    for name in wins_names
}

wins_by_normalized = {}

for name in wins_names:
    key = normalize_name(name)
    wins_by_normalized.setdefault(key, []).append(name)

# Track potential matches for review.
match_suggestions = []

for vorp_name in vorp_names:
    normalized = normalize_name(vorp_name)
    exact = wins_by_normalized.get(normalized, [])

    if len(exact) == 1:
        name_map[("vorp", vorp_name)] = exact[0]
        continue

    if len(exact) > 1:
        # Ambiguous exact matches should not be merged automatically.
        name_map[("vorp", vorp_name)] = f"VORP only: {vorp_name}"
        match_suggestions.append({
            "VORP Name": vorp_name,
            "Suggested Match": "",
            "Score": 100,
            "Status": "Ambiguous exact match",
        })
        continue

    # Prefer candidates whose team also matches.
    vorp_teams = set(
        vorp_df.loc[vorp_df["Name"] == vorp_name, "Team"]
        .map(normalize_team)
    )

    same_team_candidates = []

    for wins_name in wins_names:
        wins_teams_for_player = set(
            wins_df.loc[
                wins_df["Player"] == wins_name, "Team"
            ].map(normalize_team)
        )

        if vorp_teams & wins_teams_for_player:
            same_team_candidates.append(wins_name)

    candidates = same_team_candidates or wins_names

    results = process.extract(
        vorp_name,
        candidates,
        scorer=fuzz.WRatio,
        limit=2,
    )

    if not results:
        name_map[("vorp", vorp_name)] = f"VORP only: {vorp_name}"
        continue

    best_name, best_score, _ = results[0]
    second_score = results[1][1] if len(results) > 1 else 0

    # Automatically match only high-confidence, unambiguous matches.
    if best_score >= 96 and best_score - second_score >= 5:
        name_map[("vorp", vorp_name)] = best_name
    else:
        name_map[("vorp", vorp_name)] = f"VORP only: {vorp_name}"

        match_suggestions.append({
            "VORP Name": vorp_name,
            "Suggested Match": best_name,
            "Score": round(best_score, 1),
            "Status": "Review required",
        })


# =====================================================
# MANUAL MATCHING OVERRIDES
# =====================================================

st.header("Player Name Matching")

if "name_overrides" not in st.session_state:
    st.session_state["name_overrides"] = {}

with st.expander("Review possible name differences"):
    st.caption(
        "High-confidence matches are automatic. "
        "Review uncertain matches below. Choose 'Keep separate' "
        "if the names belong to different players."
    )

    if match_suggestions:
        with st.form("name_matching_form"):
            new_overrides = {}

            for i, item in enumerate(match_suggestions):
                vorp_name = item["VORP Name"]
                suggested = item["Suggested Match"]

                st.write(
                    f"**{vorp_name}** — "
                    f"suggestion: {suggested or 'No safe suggestion'} "
                    f"(score {item['Score']})"
                )

                options = ["Keep separate"] + wins_names

                saved = st.session_state["name_overrides"].get(
                    vorp_name, suggested
                )

                default_index = (
                    options.index(saved)
                    if saved in options
                    else 0
                )

                selected = st.selectbox(
                    f"Match {vorp_name} to",
                    options,
                    index=default_index,
                    key=f"match_{i}",
                )

                new_overrides[vorp_name] = (
                    selected if selected != "Keep separate" else None
                )

            submitted = st.form_submit_button("Save name matches")

            if submitted:
                st.session_state["name_overrides"] = new_overrides
                st.rerun()

    else:
        st.success("All player names matched automatically.")

# Apply manual overrides.
for vorp_name, wins_name in st.session_state["name_overrides"].items():
    if wins_name:
        name_map[("vorp", vorp_name)] = wins_name
    else:
        name_map[("vorp", vorp_name)] = f"VORP only: {vorp_name}"


def canonical_player(source, name):
    return name_map.get((source, name), name)


# =====================================================
# TEAM MATCHING
# =====================================================

wins_teams = sorted(wins_df["Team"].unique())
vorp_teams = sorted(vorp_df["Team"].unique())

vorp_team_lookup = {}

for team in vorp_teams:
    key = normalize_team(team)
    vorp_team_lookup.setdefault(key, []).append(team)


def get_vorp_team(wins_team):
    """Match normalized team names between datasets."""
    candidates = vorp_team_lookup.get(
        normalize_team(wins_team), []
    )

    return candidates[0] if len(candidates) == 1 else None


# =====================================================
# MATCHUP SELECTION
# =====================================================

st.header("Team Win Prediction (Wins Added & VORP)")

col1, col2 = st.columns(2)

with col1:
    team_1 = st.selectbox(
        "Select Team 1",
        wins_teams,
        key="team_1",
    )

with col2:
    available_teams = [
        team for team in wins_teams if team != team_1
    ]

    team_2 = st.selectbox(
        "Select Team 2",
        available_teams,
        key="team_2",
    )


# =====================================================
# SHARED PLAYER EXCLUSIONS
# =====================================================

def get_team_player_options(team):
    """Return shared player identities from both datasets."""
    options = set()

    # Wins Added players.
    wins_players = wins_df.loc[
        wins_df["Team"] == team, "Player"
    ].unique()

    for player in wins_players:
        options.add(canonical_player("wins", player))

    # VORP players, if the team can be matched.
    vorp_team = get_vorp_team(team)

    if vorp_team:
        vorp_players = vorp_df.loc[
            vorp_df["Team"] == vorp_team, "Name"
        ].unique()

        for player in vorp_players:
            options.add(canonical_player("vorp", player))

    return sorted(options)


st.subheader("Player Availability")

st.caption(
    "Exclude each player once. The exclusion is applied to every "
    "matching record in both datasets. Players found in only one "
    "dataset will affect only that metric."
)

col1, col2 = st.columns(2)

with col1:
    excluded_1 = st.multiselect(
        f"Exclude players from {team_1}",
        get_team_player_options(team_1),
        key="excluded_1",
    )

with col2:
    excluded_2 = st.multiselect(
        f"Exclude players from {team_2}",
        get_team_player_options(team_2),
        key="excluded_2",
    )


# =====================================================
# METRIC CALCULATIONS
# =====================================================

def calculate_wins_added(team, excluded):
    data = wins_df[wins_df["Team"] == team].copy()

    data["_canonical"] = data["Player"].map(
        lambda name: canonical_player("wins", name)
    )

    data = data[~data["_canonical"].isin(excluded)]

    return float(data["Wins Added"].sum())


def calculate_vorp(team, excluded):
    vorp_team = get_vorp_team(team)

    if vorp_team is None:
        return None

    data = vorp_df[vorp_df["Team"] == vorp_team].copy()

    data["_canonical"] = data["Name"].map(
        lambda name: canonical_player("vorp", name)
    )

    data = data[~data["_canonical"].isin(excluded)]

    return float(data["Rating"].sum())


wins_1 = calculate_wins_added(team_1, excluded_1)
wins_2 = calculate_wins_added(team_2, excluded_2)

vorp_1 = calculate_vorp(team_1, excluded_1)
vorp_2 = calculate_vorp(team_2, excluded_2)


# =====================================================
# MATCHUP DISPLAY
# =====================================================

col1, col2 = st.columns(2)

with col1:
    st.subheader(team_1)
    st.metric("Wins Added", f"{wins_1:.2f}")
    st.metric(
        "VORP",
        "Team mapping unavailable"
        if vorp_1 is None
        else f"{vorp_1:.2f}",
    )

with col2:
    st.subheader(team_2)
    st.metric("Wins Added", f"{wins_2:.2f}")
    st.metric(
        "VORP",
        "Team mapping unavailable"
        if vorp_2 is None
        else f"{vorp_2:.2f}",
    )


def prediction(team_a, team_b, score_a, score_b, metric):
    if score_a is None or score_b is None:
        return f"{metric}: unable to match both teams."

    difference = abs(score_a - score_b)

    if abs(difference) < 1e-9:
        return f"{metric}: Even matchup."

    favored = team_a if score_a > score_b else team_b

    return f"{metric}: {favored} favored by {difference:.2f}."


if st.button("Predict Matchup", type="primary"):
    st.subheader("Matchup Predictions")

    st.write(
        prediction(team_1, team_2, wins_1, wins_2, "Wins Added")
    )

    st.write(
        prediction(team_1, team_2, vorp_1, vorp_2, "VORP")
    )


# =====================================================
# TEAM RANKINGS
# =====================================================

st.header("Top Teams by Total Wins Added")

num_teams = st.slider(
    "Number of teams to display",
    min_value=1,
    max_value=min(30, len(wins_teams)),
    value=min(10, len(wins_teams)),
)

team_rankings = (
    wins_df.groupby("Team", as_index=False)["Wins Added"]
    .sum()
    .sort_values("Wins Added", ascending=False)
    .head(num_teams)
    .reset_index(drop=True)
)

team_rankings.index += 1
team_rankings["Wins Added"] = team_rankings["Wins Added"].map(
    lambda x: f"{x:.2f}"
)

st.table(team_rankings)


# =====================================================
# PLAYER PROFILE LOOKUP
# =====================================================

st.header("Player Profile Lookup")

selected_player = st.selectbox(
    "Select a Player",
    sorted(wins_df["Player"].unique()),
)

player_data = wins_df[
    wins_df["Player"] == selected_player
].iloc[0]

canonical = canonical_player("wins", selected_player)

matching_vorp_names = [
    name for name in vorp_names
    if canonical_player("vorp", name) == canonical
]

player_vorp = None

if matching_vorp_names:
    rows = vorp_df[
        vorp_df["Name"] == matching_vorp_names[0]
    ]

    if not rows.empty:
        player_vorp = rows.iloc[0]["Rating"]


st.subheader(selected_player)

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Team", player_data["Team"])

    if "Production Value (Millions)" in wins_df.columns:
        st.metric(
            "Production Value",
            f"${player_data['Production Value (Millions)']:.2f}M",
        )

    if "Possesions" in wins_df.columns:
        st.metric(
            "Possessions",
            f"{player_data['Possesions']:.0f}",
        )

with col2:
    if "RAPM over replacement" in wins_df.columns:
        st.metric(
            "RAPM Over Replacement",
            f"{player_data['RAPM over replacement']:.2f}",
        )

    if "AAV" in wins_df.columns:
        st.metric("AAV", f"${player_data['AAV']:.2f}M")

    st.metric(
        "VORP",
        "Not found"
        if player_vorp is None
        else f"{player_vorp:.2f}",
    )

with col3:
    st.metric("Wins Added", f"{player_data['Wins Added']:.2f}")

    if "Net Value" in wins_df.columns:
        st.metric(
            "Net Value",
            f"{player_data['Net Value']:.2f}M",
        )


# =====================================================
# WINS ADDED PLAYER LEADERBOARD
# =====================================================

st.header("Player Leaderboards")

available_stats = [
    stat for stat in [
        "RAPM over replacement",
        "Wins Added",
        "Production Value (Millions)",
        "Net Value",
    ]
    if stat in wins_df.columns
]

stat_choice = st.selectbox(
    "Select Stat to Rank Players",
    available_stats,
)

num_players = st.slider(
    "Number of players to display",
    min_value=1,
    max_value=len(wins_df),
    value=min(10, len(wins_df)),
)

leaderboard = (
    wins_df.sort_values(stat_choice, ascending=False)
    .head(num_players)
    .reset_index(drop=True)
)

leaderboard.index += 1

leaderboard_display = leaderboard[
    ["Player", "Team", stat_choice]
].copy()

leaderboard_display[stat_choice] = (
    leaderboard_display[stat_choice].map(lambda x: f"{x:.2f}")
)

st.table(leaderboard_display)


# =====================================================
# VORP PLAYER LEADERBOARD
# =====================================================

st.subheader("VORP Player Leaderboard")

num_vorp_players = st.slider(
    "Number of VORP players to display",
    min_value=1,
    max_value=len(vorp_df),
    value=min(10, len(vorp_df)),
    key="vorp_slider",
)

vorp_leaderboard = (
    vorp_df.sort_values("Rating", ascending=False)
    .head(num_vorp_players)
    .reset_index(drop=True)
)

vorp_leaderboard.index += 1

vorp_display = vorp_leaderboard[
    ["Name", "Team", "Rating"]
].copy()

vorp_display["Rating"] = vorp_display["Rating"].map(
    lambda x: f"{x:.2f}"
)

st.table(vorp_display)
