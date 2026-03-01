import streamlit as st
import requests
import json
from openai import OpenAI
from datetime import datetime
from streamlit_geolocation import streamlit_geolocation
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURATION & SECRETS
# ==========================================
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# Initialize Supabase Client
@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_supabase()

# ==========================================
# 2. CUSTOM CSS & STYLING
# ==========================================
st.set_page_config(page_title="Get Wild", page_icon="🌿", layout="centered")

custom_css = """
<style>
    .hero-header { text-align: center; padding: 2rem 0 1rem 0; }
    .hero-title { color: #2e7d32; font-family: 'Helvetica Neue', sans-serif; font-size: 3.5rem; font-weight: 800; letter-spacing: -1px; text-transform: uppercase; margin-bottom: 0; line-height: 1.1; }
    .hero-subtitle { color: #558b2f; font-size: 1.2rem; font-weight: 400; letter-spacing: 1px; margin-top: 10px; }
    .take-me-there-btn { display: inline-block; background-color: #2e7d32; color: white !important; text-align: center; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; letter-spacing: 0.5px; width: 100%; transition: all 0.3s ease; margin-top: 10px; }
    .take-me-there-btn:hover { background-color: #1b5e20; box-shadow: 0 4px 12px rgba(46, 125, 50, 0.3); }
    .wild-card { background: linear-gradient(135deg, #f1f8e9 0%, #dcedc8 100%); border-left: 6px solid #558b2f; border-radius: 12px; padding: 25px; margin-top: 20px; box-shadow: 0 8px 24px rgba(0,0,0,0.08); animation: fadeSlideUp 0.8s ease-out forwards; opacity: 0; transform: translateY(20px); }
    @keyframes fadeSlideUp { to { opacity: 1; transform: translateY(0); } }
    div[role="radiogroup"] { gap: 1rem; }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# ==========================================
# 3. SESSION STATE MANAGEMENT
# ==========================================
if 'user' not in st.session_state:
    st.session_state.user = None

# ==========================================
# 4. HELPER FUNCTIONS (The Engine)
# ==========================================
def get_coordinates(location_query):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={location_query}&key={GOOGLE_API_KEY}"
    response = requests.get(url).json()
    if response['status'] == 'OK':
        loc = response['results'][0]['geometry']['location']
        return loc['lat'], loc['lng']
    return None, None

def build_semantic_query(filters_dict):
    modifiers = []
    if filters_dict['group'] == "Date": modifiers.append("romantic")
    elif filters_dict['group'] == "Family Outing": modifiers.append("kid-friendly")
    elif filters_dict['group'] == "Friends": modifiers.append("fun lively")
    elif filters_dict['group'] == "Solo": modifiers.append("cozy")

    if filters_dict.get('specific'): modifiers.append(filters_dict['specific'])
    modifier_str = " ".join(modifiers)
    
    if filters_dict['vibe'] == "Outside":
        if filters_dict['food'] == "Full Meal": base = "restaurants, patios, or wineries with outdoor dining"
        elif filters_dict['food'] == "Just Drinks/Coffee": base = "breweries, wineries, or outdoor bars with patios"
        else: base = "botanical gardens, outdoor attractions, mini golf, scenic trails, or parks"
    else:
        if filters_dict['food'] == "Full Meal": base = "restaurants"
        elif filters_dict['food'] == "Just Drinks/Coffee": base = "bars, cafes, or lounges"
        else: base = "entertainment activities, museums, or indoor attractions"
            
    return f"{modifier_str} {base}".strip()

def fetch_places_semantic(semantic_query, lat, lng, radius_miles):
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.types,places.regularOpeningHours,places.priceLevel,places.editorialSummary"
    }
    radius_meters = int(radius_miles * 1609.34)
    data = {
        "textQuery": semantic_query,
        "pageSize": 20,
        "locationBias": {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_meters}
        }
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        raise Exception(f"Google API Error: {response.text}")
    return response.json().get('places', [])

def fetch_live_events(location_name, intended_time, group_type, current_date):
    url = "https://api.tavily.com/search"
    query = f"Find specific local events, live music, festivals, trivia nights, or pop-ups happening on {intended_time} strictly in or near {location_name}. Today's date is {current_date}. List exact event names and locations suitable for a {group_type}."
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "include_answer": True,
        "max_results": 3
    }
    try:
        response = requests.post(url, json=payload)
        data = response.json()
        answer = data.get("answer", "")
        context = " ".join([res.get("content", "") for res in data.get("results", [])])
        return f"TAVILY AI WEB SEARCH SUMMARY: {answer} \n\nRAW WEB CONTEXT: {context}"
    except Exception as e:
        return "No live event data found."

def get_ai_recommendations(raw_places, live_events_data, filters_dict, location_name, current_date, mode="top_3"):
    client = OpenAI(api_key=OPENAI_API_KEY)
    intended_time = filters_dict['time']
    specific_request = filters_dict.get('specific', '')
    
    if mode == "get_wild":
        instruction = """
        Select EXACTLY ONE option from the data. 
        It must be an unexpected, spontaneous adventure.
        Assign it the category: "Spontaneous Adventure".
        """
    else:
        instruction = """
        Return EXACTLY 3 options from the data, structured strictly as:
        1. The Crowd-Pleaser: Established, highly-rated, local favorite.
        2. The Fresh Take / Live Event: You MUST heavily prioritize the 'LIVE WEB SEARCH EVENTS' data. If a valid local event (trivia, live music, festival, etc.) is happening, feature it here.
        3. The Hidden Gem: A spot that feels unique. If you cannot find a true hidden gem in the provided data, just pick the most interesting real place available.
        """

    system_prompt = f"""
    You are a luxury local concierge for an app called 'Get Wild'.
    
    CRITICAL CONTEXT:
    - User Location: {location_name}
    - Today's Date: {current_date}
    - User Intended Time: {intended_time}
    - User Profile: {filters_dict['group']} looking for {filters_dict['food']} in a {filters_dict['vibe']} setting.
    - SPECIAL REQUEST: "{specific_request if specific_request else 'None'}"
    
    GEOGRAPHY & HALLUCINATION SHACKLES (MANDATORY):
    1. DO NOT INVENT PLACES. If a place is not explicitly in the data below, you cannot recommend it.
    2. STRICT GEOGRAPHY: The location MUST be physically located in or immediately bordering {location_name}. Ignore web search events from other states.
    3. STRICT TIME: Compare 'Today's Date' to the events. Do not recommend past events.
    
    DATA SOURCES:
    1. GOOGLE PLACES DATA: A list of established local venues.
    2. LIVE WEB SEARCH EVENTS: Live data scraped from the web.
    
    {instruction}
    
    Return STRICTLY as a JSON object with a 'recommendations' array containing:
    'name', 'category', 'address', 'why_its_perfect' (2 sentences proving why it fits. If it's a live event, state the date/time!), and 'vibe_check' (3 words).
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"GOOGLE PLACES DATA: {json.dumps(raw_places)}\n\nLIVE WEB SEARCH EVENTS:\n{live_events_data}"}
        ]
    )
    return json.loads(response.choices[0].message.content)


# ==========================================
# 5. UI ROUTING (Login vs Main App)
# ==========================================
st.markdown("""
<div class="hero-header">
    <h1 class="hero-title">Get Wild</h1>
    <p class="hero-subtitle">Disconnect. Explore. Breathe.</p>
</div>
""", unsafe_allow_html=True)

# --- AUTHENTICATION SCREEN ---
if st.session_state.user is None:
    st.write("---")
    st.subheader("Welcome to the Wild.")
    st.write("Create an account or log in to personalize your adventures and save your favorite spots.")
    
    tab1, tab2 = st.tabs(["Log In", "Sign Up"])
    
    with tab1:
        with st.form("login_form"):
            email_login = st.text_input("Email")
            password_login = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Log In", type="primary", use_container_width=True)
            
            if submit_login:
                try:
                    res = supabase.auth.sign_in_with_password({"email": email_login, "password": password_login})
                    st.session_state.user = res.user
                    st.rerun()
                except Exception as e:
                    st.error("Login failed. Check your credentials.")

    with tab2:
        with st.form("signup_form"):
            email_signup = st.text_input("Email")
            password_signup = st.text_input("Password", type="password", help="Must be at least 6 characters.")
            submit_signup = st.form_submit_button("Sign Up", type="primary", use_container_width=True)
            
            if submit_signup:
                try:
                    res = supabase.auth.sign_up({"email": email_signup, "password": password_signup})
                    st.success("Account created successfully! You can now log in.")
                except Exception as e:
                    st.error(f"Signup failed: {e}")

# --- MAIN APPLICATION SCREEN ---
else:
    # Logout Button in the top right
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("Log Out"):
            supabase.auth.sign_out()
            st.session_state.user = None
            st.rerun()
            
    st.write("---")
    
    # --- Location Section ---
    st.subheader("Where are we going?")
    loc_col1, loc_col2 = st.columns([5, 1])
    with loc_col1:
        location_input = st.text_input("Location", placeholder="Enter City or ZIP Code (e.g., Fairfax, VA)", label_visibility="collapsed")
    with loc_col2:
        geo_data = streamlit_geolocation()

    gps_active = False
    if geo_data and geo_data.get('latitude') is not None:
        gps_active = True
        st.success("🌿 GPS Location Locked!")

    st.write("---")
    st.subheader("What's the plan?")

    col_day, col_time = st.columns(2)
    with col_day:
        day_choice = st.radio("Day", ["☀️ Today", "📅 Tomorrow"], horizontal=True, label_visibility="collapsed")
    with col_time:
        time_choice = st.radio("Time", ["☀️ Daytime", "🌙 Night"], horizontal=True, label_visibility="collapsed")

    intended_time = f"{day_choice} ({time_choice})"
    st.write("") 

    col_group, col_vibe = st.columns(2)
    with col_group:
        group_type = st.selectbox("Who is going?", ["Date", "Family Outing", "Friends", "Solo"])
    with col_vibe:
        vibe = st.radio("Setting?", ["Doesn't Matter", "Outside", "Inside"], horizontal=True)
    st.write("") 

    col_food, col_dist = st.columns(2)
    with col_food:
        food_pref = st.selectbox("Sustenance?", ["Full Meal", "Just Drinks/Coffee", "No Food Needed"])
    with col_dist:
        distance = st.slider("Max Distance (Miles)", 1, 20, 5)

    with st.expander("Need something specific? (Optional)", expanded=False):
        specific_request = st.text_input("Keyword", placeholder="e.g., 'live jazz', 'vegan options'", label_visibility="collapsed")

    filters_dict = {
        "group": group_type,
        "time": intended_time,
        "vibe": vibe,
        "food": food_pref,
        "specific": specific_request
    }

    st.write("---")
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        top_3_clicked = st.button("🌟 Top 3 Recommendations", use_container_width=True)
    with btn_col2:
        get_wild_clicked = st.button("🎲 GET WILD", type="primary", use_container_width=True)

    # --- EXECUTION LOGIC ---
    if top_3_clicked or get_wild_clicked:
        mode = "get_wild" if get_wild_clicked else "top_3"
        
        if not location_input and not gps_active:
            st.warning("Please enter a location or click the GPS icon first!")
        else:
            results = None 
            
            with st.spinner("Scouting the wild..."):
                try:
                    current_date = datetime.now().strftime("%A, %B %d, %Y")
                    
                    location_context = location_input
                    if gps_active:
                        lat, lng = geo_data['latitude'], geo_data['longitude']
                        location_context = "their exact GPS coordinates"
                    else:
                        lat, lng = get_coordinates(location_input)
                    
                    if lat is None:
                        st.error("Couldn't find that location.")
                    else:
                        semantic_query = build_semantic_query(filters_dict)
                        raw_places = fetch_places_semantic(semantic_query, lat, lng, distance)
                        
                        live_events_data = fetch_live_events(location_input if location_input else "nearby", intended_time, group_type, current_date)
                        
                        results = get_ai_recommendations(raw_places, live_events_data, filters_dict, location_context, current_date, mode=mode)
                        
                except Exception as e:
                    st.error(f"Whoops! Something went wrong out in the wild: {e}")
                    
            if results:
                if mode == "get_wild":
                    spot = results.get("recommendations", [])[0]
                    search_term = spot['name'].replace(' ', '+') + f"+{location_input.replace(' ', '+')}"
                    map_url = f"https://www.google.com/maps/search/?api=1&query={search_term}"
                    
                    html_card = f"""
                    <div class="wild-card">
                        <h4 style="color: #2e7d32; margin-top: 0;">Start Your Adventure</h4>
                        <h2>{spot['name']}</h2>
                        <p>📍 <strong>{spot['address']}</strong> | ✨ <i>{spot['vibe_check']}</i></p>
                        <p style="font-size: 1.1rem; line-height: 1.5;">{spot['why_its_perfect']}</p>
                        <a href="{map_url}" target="_blank" class="take-me-there-btn">Take me there!</a>
                    </div>
                    """
                    st.markdown(html_card, unsafe_allow_html=True)
                    
                else:
                    st.write("### Your Handpicked Spots:")
                    for spot in results.get("recommendations", []):
                        with st.container():
                            st.markdown(f"<span style='color: #558b2f; font-weight: 700; text-transform: uppercase; font-size: 0.85rem; letter-spacing: 1px;'>{spot.get('category', 'Top Pick')}</span>", unsafe_allow_html=True)
                            st.subheader(spot['name'])
                            st.caption(f"📍 {spot['address']} | ✨ **{spot['vibe_check']}**")
                            st.write(spot['why_its_perfect'])
                            
                            search_term = spot['name'].replace(' ', '+') + f"+{location_input.replace(' ', '+')}"
                            map_url = f"https://www.google.com/maps/search/?api=1&query={search_term}"
                            st.markdown(f'<a href="{map_url}" target="_blank" class="take-me-there-btn">Take me there!</a>', unsafe_allow_html=True)
                            st.write("---")