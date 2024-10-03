import streamlit as st
import pandas as pd

# Load CSV files
@st.cache_data
def load_data():
    metric_1 = pd.read_csv('vorp.csv')
    metric_2 = pd.read_csv('darko.csv')
    metric_3 = pd.read_csv('winshares.csv')
    metric_4 = pd.read_csv('cavdaws.csv')
    return metric_1, metric_2, metric_3, metric_4

metric_1, metric_2, metric_3, metric_4 = load_data()

# Dictionary to map metric names to dataframes
metrics = {
    "VORP": metric_1,
    "DARKO": metric_2,
    "Win Shares": metric_3,
    "CAVDAWS": metric_4
}

# Function to calculate the sum of ratings by team, excluding selected players
def calculate_team_sum(df, team, excluded_players):
    team_data = df[df['Team'] == team]
    team_data = team_data[~team_data['Name'].isin(excluded_players)]
    return team_data['Rating'].sum()

# Function to calculate total rating for all teams
def calculate_total_team_ratings(df):
    return df.groupby('Team')['Rating'].sum().reset_index()

# Main app structure
st.title("NBA Player Rating Dashboard")

# Sidebar for metric selection
metric_choice = st.sidebar.selectbox("Select Metric", options=list(metrics.keys()))

# Load the corresponding dataframe for the selected metric
metric_df = metrics[metric_choice]

# Display team options and sum calculations for two teams
st.header(f"Team Rating Comparison for {metric_choice}")

# Select two teams to compare
teams = metric_df['Team'].unique()
team_1 = st.selectbox("Select Team 1", teams)
team_2 = st.selectbox("Select Team 2", teams)

if team_1 and team_2:
    st.write(f"Selected Teams: {team_1} vs {team_2}")

    # Allow users to exclude players from Team 1 and Team 2
    excluded_team_1 = st.multiselect(
        f"Exclude players from {team_1}", 
        metric_df[metric_df['Team'] == team_1]['Name'].tolist(), 
        key="excluded_team_1"
    )
    excluded_team_2 = st.multiselect(
        f"Exclude players from {team_2}", 
        metric_df[metric_df['Team'] == team_2]['Name'].tolist(), 
        key="excluded_team_2"
    )

    # Calculate sums for each team
    team_1_sum = calculate_team_sum(metric_df, team_1, excluded_team_1)
    team_2_sum = calculate_team_sum(metric_df, team_2, excluded_team_2)

    st.write(f"Total rating for {team_1} (excluding selected players): {team_1_sum}")
    st.write(f"Total rating for {team_2} (excluding selected players): {team_2_sum}")

# Calculate the difference between the two team sums
    difference = abs(team_1_sum - team_2_sum)

    # Display matchup prediction with the difference
    if st.button("Predict Matchup"):
        if team_1_sum > team_2_sum:
            st.write(f"{team_1} is predicted to win with a difference of {difference:.2f}!")
        elif team_1_sum < team_2_sum:
            st.write(f"{team_2} is predicted to win with a differnence of {difference:.2f}!")
        else:
            st.write("It's a tie!")

# Display the top teams based on the selected metric
st.header(f"Top Teams by Total Rating for {metric_choice}")

# Allow user to select how many top teams to display
num_teams = st.slider("Select the number of top teams to display", min_value=1, max_value=30, value=10)

# Calculate total ratings for all teams and sort
total_team_ratings = calculate_total_team_ratings(metric_df)
total_team_ratings = total_team_ratings.sort_values(by='Rating', ascending=False).head(num_teams)

# Round the 'Rating' column to one decimal place and convert to string for display
total_team_ratings['Rating'] = total_team_ratings['Rating'].map(lambda x: f"{x:.1f}")

# Reset the index to start from 1
total_team_ratings = total_team_ratings.reset_index(drop=True)
total_team_ratings.index += 1  # Set the index to start at 1

# Display the top teams in a table
st.table(total_team_ratings[['Team', 'Rating']])

# Display the top players based on the selected metric
st.header(f"Top Players by Rating for {metric_choice}")

# Allow user to select how many top players to display
num_players = st.slider("Select the number of top players to display", min_value=1, max_value=100, value=10)

# Sort the players by rating in descending order and select the top N players
top_players = metric_df.sort_values(by='Rating', ascending=False).head(num_players)

# Reset the index to start from 1, and drop the old index
top_players = top_players.reset_index(drop=True)
top_players.index += 1  # Set the index to start at 1

# Round the 'Rating' column to one decimal place and convert to string for display
top_players['Rating'] = top_players['Rating'].map(lambda x: f"{x:.1f}")

# Display the top players in a table
st.table(top_players[['Name', 'Team', 'Rating']])
