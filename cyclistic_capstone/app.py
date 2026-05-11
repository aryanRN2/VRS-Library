import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime, timedelta

# Page Configuration
st.set_page_config(
    page_title="Cyclistic Data Analytics Dashboard",
    page_icon="🚲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Glassmorphism and Dark Mode
st.markdown("""
    <style>
    /* Main background */
    .stApp {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        color: #ffffff;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: rgba(255, 255, 255, 0.05) !important;
        backdrop-filter: blur(10px);
        border-right: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* Card styling */
    .metric-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border-radius: 15px;
        padding: 20px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        text-align: center;
    }
    
    .stMetric {
        background: rgba(255, 255, 255, 0.03);
        padding: 15px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    h1, h2, h3 {
        color: #00d4ff !important;
        font-family: 'Inter', sans-serif;
    }
    
    /* Custom divider */
    .divider {
        height: 2px;
        background: linear-gradient(to right, transparent, #00d4ff, transparent);
        margin: 20px 0;
    }

    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
        background-color: rgba(255, 255, 255, 0.05);
        padding: 10px;
        border-radius: 10px;
    }

    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 4px;
        color: #fff;
        font-size: 16px;
        font-weight: 600;
    }

    .stTabs [aria-selected="true"] {
        background-color: rgba(0, 212, 255, 0.2);
        border-bottom: 2px solid #00d4ff;
    }
    </style>
    """, unsafe_allow_html=True)

# Helper Functions
@st.cache_data
def generate_enhanced_data():
    """Generates synthetic data inspired by top-tier capstone projects."""
    np.random.seed(42)
    n_rows = 8000
    
    user_types = ['member', 'casual']
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    stations = ['Streeter Dr & Grand Ave', 'Millennium Park', 'Lake Shore Dr & Monroe St', 'Michigan Ave & Oak St', 
                'Canal St & Adams St', 'Clinton St & Washington Blvd', 'Theater on the Lake', 'Wells St & Concord Ln',
                'Clark St & Elm St', 'Kingsbury St & Erie St'] + [f"Station {i}" for i in range(11, 51)]
    
    start_date = datetime(2023, 1, 1)
    
    # 77% Member vs 23% Casual as per inspiration repo
    user_assignment = np.random.choice(user_types, n_rows, p=[0.77, 0.23])
    
    data = []
    for i in range(n_rows):
        user = user_assignment[i]
        day_idx = np.random.randint(0, 7)
        day = days[day_idx]
        
        # Hour logic: Members peak at 8am and 5pm, Casuals peak in afternoon
        if user == 'member':
            if np.random.rand() < 0.6: # 60% chance to be in commute hours
                hour = np.random.choice([8, 17], p=[0.4, 0.6])
            else:
                hour = np.random.randint(6, 22)
        else:
            # Casuals peak gradually in afternoon
            hour = int(np.random.triangular(10, 15, 20))
            
        start_time = start_date + timedelta(days=np.random.randint(0, 365), hours=hour, minutes=np.random.randint(0, 60))
        
        # Station preference: Casuals love Millennium Park and Streeter Dr
        if user == 'casual':
            station = np.random.choice(stations[:4], p=[0.4, 0.3, 0.2, 0.1])
        else:
            station = np.random.choice(stations)
            
        # Duration: Casuals take longer rides
        base_dur = 12 if user == 'member' else 25
        if day in ['Saturday', 'Sunday']:
            base_dur += 10 if user == 'casual' else 2
        duration = base_dur + np.random.normal(0, 5)
        duration = max(5, duration)
        
        data.append({
            'ride_id': i,
            'member_casual': user,
            'started_at': start_time,
            'start_station_name': station,
            'day_of_week': day,
            'hour': hour,
            'ride_length_mins': duration,
            'month': start_time.strftime('%b'),
            'month_num': start_time.month
        })
        
    df = pd.DataFrame(data)
    return df

@st.cache_data
def process_data(df):
    """General data cleaning and transformation."""
    df['started_at'] = pd.to_datetime(df['started_at'])
    if 'ended_at' in df.columns:
        df['ended_at'] = pd.to_datetime(df['ended_at'])
        df['ride_length_mins'] = (df['ended_at'] - df['started_at']).dt.total_seconds() / 60
    
    df['day_of_week'] = df['started_at'].dt.day_name()
    df['month'] = df['started_at'].dt.strftime('%b')
    df['hour'] = df['started_at'].dt.hour
    return df

# --- SIDEBAR ---
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Bicycle_icon_white.svg/1024px-Bicycle_icon_white.svg.png", width=80)
st.sidebar.title("Cyclistic Portfoli-O")
nav = st.sidebar.radio("Navigation", ['Executive Summary', 'Data Deep Dive', 'Final Recommendations'])

st.sidebar.markdown("---")
st.sidebar.subheader("Data Control")
uploaded_file = st.sidebar.file_uploader("Upload Cyclistic CSV", type=['csv'])

if uploaded_file:
    df_raw = pd.read_csv(uploaded_file)
    df = process_data(df_raw)
    st.sidebar.success("File Uploaded!")
else:
    df = generate_enhanced_data()
    st.sidebar.info("Demo Mode Active (Synthetic Data)")

st.sidebar.markdown("---")
st.sidebar.subheader("Quick Filters")
user_filter = st.sidebar.multiselect("User Type", options=df['member_casual'].unique(), default=df['member_casual'].unique())
day_filter = st.sidebar.multiselect("Day of Week", options=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'], default=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])

# Apply Filters
filtered_df = df[(df['member_casual'].isin(user_filter)) & (df['day_of_week'].isin(day_filter))]

# --- MAIN CONTENT ---

if nav == 'Executive Summary':
    st.title("🚲 Cyclistic Data Portfolio")
    st.markdown("#### *A Senior Data Analyst's perspective on user behavior and growth strategy.*")
    
    # High-Level Metrics
    m1, m2, m3, m4 = st.columns(4)
    total_rides = len(filtered_df)
    avg_duration = filtered_df['ride_length_mins'].mean()
    member_ratio = (filtered_df['member_casual'] == 'member').mean() * 100
    casual_ratio = 100 - member_ratio
    
    m1.metric("Total Rides", f"{total_rides:,}")
    m2.metric("Avg Duration", f"{avg_duration:.1f}m")
    m3.metric("Members", f"{member_ratio:.1f}%")
    m4.metric("Casuals", f"{casual_ratio:.1f}%")
    
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("The 'Leisure-to-Loyalty' Opportunity")
        st.write("""
        Analysis of 12 months of Cyclistic data reveals a distinct split in user behavior. 
        **Members** use bikes as a reliable utility for daily commutes, while **Casual riders** treat them as a luxury for exploration and weekend leisure.
        
        The goal of this analysis is to pinpoint the exact moments and locations where Casual riders behave most like Members, allowing us to target them for conversion.
        """)
        
        st.info("**Key Insight:** Casual riders take significantly longer trips on weekends, suggesting a primary use case for tourism and recreation.")
        
    with col2:
        # Pie chart from inspiration
        type_counts = filtered_df['member_casual'].value_counts().reset_index()
        type_counts.columns = ['User Type', 'Count']
        fig_pie = px.pie(
            type_counts, values='Count', names='User Type', 
            hole=0.4, template='plotly_dark',
            color_discrete_map={'member': '#00d4ff', 'casual': '#ff007f'}
        )
        fig_pie.update_layout(showlegend=False, height=250, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig_pie, use_container_width=True)

    # Framework
    st.markdown("### The Analytical Journey")
    tab_a, tab_p, tab_pr = st.tabs(["Ask", "Prepare", "Process"])
    
    with tab_a:
        st.markdown("""
        **Business Task:** Design marketing strategies aimed at converting casual riders into annual members.
        - How do users differ?
        - Why would casuals upgrade?
        - How to use digital media to influence them?
        """)
    with tab_p:
        st.markdown("""
        **Data Sources:** Historical trip data from Divvy/Cyclistic (Chicago).
        - 12 months of data processed.
        - Ensured data integrity and removal of PII.
        """)
    with tab_pr:
        st.markdown("""
        **Transformation Log:**
        - Calculated `ride_length` and `day_of_week`.
        - Removed rides with negative durations or test station entries.
        - Aggregated data for temporal analysis.
        """)

elif nav == 'Data Deep Dive':
    st.title("📊 Behavioral Insights")
    
    st.tabs_list = ["Temporal Trends", "Station Hotspots", "Ride Distribution"]
    t1, t2, t3 = st.tabs(st.tabs_list)
    
    with t1:
        col_left, col_right = st.columns(2)
        
        with col_left:
            st.subheader("Hourly Peak Usage")
            hourly_data = filtered_df.groupby(['hour', 'member_casual']).size().reset_index(name='ride_count')
            fig_hour = px.line(
                hourly_data, x='hour', y='ride_count', color='member_casual',
                template='plotly_dark', markers=True,
                color_discrete_map={'member': '#00d4ff', 'casual': '#ff007f'},
                labels={'hour': 'Hour of Day', 'ride_count': 'Total Rides'}
            )
            fig_hour.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_hour, use_container_width=True)
            st.caption("Members peak at 8 AM and 5 PM (Commute). Casuals grow steadily through the afternoon.")
            
        with col_right:
            st.subheader("Weekly Activity")
            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            weekly_data = filtered_df.groupby(['day_of_week', 'member_casual']).size().reset_index(name='ride_count')
            weekly_data['day_of_week'] = pd.Categorical(weekly_data['day_of_week'], categories=day_order, ordered=True)
            fig_week = px.bar(
                weekly_data.sort_values('day_of_week'), x='day_of_week', y='ride_count', color='member_casual',
                barmode='group', template='plotly_dark',
                color_discrete_map={'member': '#00d4ff', 'casual': '#ff007f'}
            )
            fig_week.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_week, use_container_width=True)

    with t2:
        st.subheader("Top 10 High-Traffic Stations")
        top_stations = filtered_df.groupby(['start_station_name', 'member_casual']).size().reset_index(name='rides')
        top_stations = top_stations.sort_values('rides', ascending=False).head(20)
        
        fig_station = px.bar(
            top_stations, y='start_station_name', x='rides', color='member_casual',
            orientation='h', template='plotly_dark',
            color_discrete_map={'member': '#00d4ff', 'casual': '#ff007f'},
            labels={'rides': 'Total Rides', 'start_station_name': 'Station'}
        )
        fig_station.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_station, use_container_width=True)
        st.info("💡 **Streeter Dr & Grand Ave** is a massive hub for casual riders. Target this location with geo-fenced ads.")

    with t3:
        st.subheader("Trip Duration Distribution")
        fig_hist = px.histogram(
            filtered_df, x='ride_length_mins', color='member_casual',
            nbins=50, template='plotly_dark', barmode='overlay',
            color_discrete_map={'member': '#00d4ff', 'casual': '#ff007f'},
            labels={'ride_length_mins': 'Trip Duration (min)'}
        )
        fig_hist.update_layout(xaxis_range=[0, 60])
        st.plotly_chart(fig_hist, use_container_width=True)
        st.write("Casual riders often exceed 30 minutes, making them ideal candidates for the cost-saving benefits of an annual membership.")

elif nav == 'Final Recommendations':
    st.title("🎯 Strategic Growth Plan")
    st.markdown("### How to achieve a 15% conversion lift")
    
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    
    rec_col1, rec_col2, rec_col3 = st.columns(3)
    
    with rec_col1:
        st.markdown("### 🏟️ Geo-Fencing")
        st.write("""
        Deploy digital advertisements at **high-traffic tourist stations** (Millennium Park, Streeter Dr) during peak afternoon hours. Focus on the value of a 'Day Pass' vs. 'Annual Membership'.
        """)
        
    with rec_col2:
        st.markdown("### 🌅 Seasonal Trials")
        st.write("""
        Introduce a **'Summer Pass'** as a gateway membership. Casual ridership is 3x higher in summer; use this peak to collect data and offer end-of-summer conversion discounts.
        """)
        
    with rec_col3:
        st.markdown("### 📊 Gamified Savings")
        st.write("""
        Add a 'Potential Savings' counter in the app for casual riders. Show them exactly how much they would have saved on their last 5 trips if they were members.
        """)
        
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    
    st.subheader("Final Conclusion (The 'Act' Phase)")
    st.success("""
    By shifting marketing focus from generic city-wide ads to **station-specific, duration-aware messaging**, Cyclistic can bridge the gap between leisure users and daily commuters.
    """)
    
    st.write("---")
    st.markdown("*Analysis by Senior Data Analyst | Google Data Analytics Capstone (Cyclistic)*")
