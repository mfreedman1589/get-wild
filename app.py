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
# 3. SESSION STATE & DATABASE HELPERS
# ==========================================
if 'user' not in st.session_state:
    st.session_state.user = None
if 'current_results' not in st.session_state:
    st.session_state.current_results = None 
if 'current_mode' not in st.session_state:
    st.session_state.current_mode = None

def get_profile(user_id):
    try:
        res = supabase.table('user_profiles').select('*').eq('id', user_id).execute()
        return res.data[0] if res.data else None
    except: return None

def save_spot_to_db(user_id, name, address, category):
    try:
        supabase.table('saved_spots').insert({
            'user_id': user_id, 'spot_name': name, 'address': address, 'category': category
        }).execute()
        st.toast(f"✅ Saved {name} to your list!")
    except Exception as e:
        st.error("Failed to save spot.")

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

def build_semantic_query(filters_dict, profile):
    modifiers = []
    if filters_dict['group'] == "Date": modifiers.append("romantic")
    elif filters_dict['group'] == "Family Outing": modifiers.append("kid-friendly")
    elif filters_dict['group'] == "Friends": modifiers.append("fun lively")
    elif filters_dict['group'] == "Solo": modifiers.append("cozy")

    # Inject Profile Preferences
    if profile:
        if profile.get('needs_dog_friendly') and filters_dict['vibe'] == "Outside": modifiers.append("dog-friendly")
        if profile.get('vibe_preference'): modifiers.append(profile.get('vibe_preference'))

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
    if response.status_code != 200: raise Exception(f"Google API Error: {response.text}")
    return response.json().get('places', [])

def fetch_live_events(location_name, intended_time, group_type, current_date):
    url = "https://api.tavily.com/search"
    query = f"Find specific local events, live music, festivals, trivia nights, or pop-ups happening on {intended_time} strictly in or near {location_name}. Today's date is {current_date}. List exact event names and locations suitable for a {group_type}."
    payload = {"api_key": TAVILY_API_KEY, "query": query, "search_depth": "basic", "include_answer": True, "max_results": 3}
    try:
        response = requests.post(url, json=payload)
        data = response.json()
        return f"TAVILY AI WEB SEARCH SUMMARY: {data.get('answer', '')} \n\nRAW WEB CONTEXT: {' '.join([res.get('content', '') for res in data.get('results', [])])}"
    except: return "No live event data found."

def get_ai_recommendations(raw_places, live_events_data, filters_dict, location_name, current_date, profile, mode="top_3"):
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    profile_context = ""
    if profile:
        stroller = "MUST be stroller accessible." if profile.get('needs_stroller_access') else ""
        dog = "MUST be dog-friendly." if profile.get('needs_dog_friendly') and filters_dict['vibe'] == "Outside" else ""
        vibe_pref = f"Prioritize locations matching this vibe: {profile.get('vibe_preference')}." if profile.get('vibe_preference') else ""
        partner = f"The user's partner is named {profile.get('partner_name')}." if profile.get('partner_name') else ""
        profile_context = f"\nUSER BASELINE PROFILE:\n{stroller}\n{dog}\n{vibe_pref}\n{partner}"

    instruction = """Select EXACTLY ONE option from the data. It must be an unexpected, spontaneous adventure. Assign it the category: 'Spontaneous Adventure'.""" if mode == "get_wild" else """Return EXACTLY 3 options from the data, structured strictly as:
        1. The Crowd-Pleaser: Established, highly-rated, local favorite.
        2. The Fresh Take / Live Event: You MUST heavily prioritize the 'LIVE WEB SEARCH EVENTS' data.
        3. The Hidden Gem: A spot that feels unique. Pick the most interesting real place available."""

    system_prompt = f"""
    You are a luxury local concierge for an app called 'Get Wild'.
    
    CRITICAL CONTEXT:
    - User Location: {location_name}
    - Today's Date: {current_date}
    - User Intended Time: {filters_dict['time']}
    - Session Profile: {filters_dict['group']} looking for {filters_dict['food']} in a {filters_dict['vibe']} setting.
    - SPECIAL REQUEST: "{filters_dict.get('specific') if filters_dict.get('specific') else 'None'}"
    {profile_context}
    
    GEOGRAPHY & HALLUCINATION SHACKLES (MANDATORY):
    1. DO NOT INVENT PLACES. Must be in the provided data.
    2. STRICT GEOGRAPHY: Must be physically in or immediately bordering {location_name}.
    3. STRICT TIME: Do not recommend past events.
    
    DATA SOURCES:
    1. GOOGLE PLACES DATA: A list of established local venues.
    2. LIVE WEB SEARCH EVENTS: Live data scraped from the web.
    
    {instruction}
    
    Return STRICTLY as a JSON object with a 'recommendations' array containing:
    'name', 'category', 'address', 'why_its_perfect' (2 sentences. Weave in how it matches their Baseline Profile if applicable!), and 'vibe_check' (3 words).
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
# 5. UI ROUTING
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
    
    tab_login, tab_signup = st.tabs(["Log In", "Sign Up"])
    with tab_login:
        with st.form("login_form"):
            email_login = st.text_input("Email")
            password_login = st.text_input("Password", type="password")
            if st.form_submit_button("Log In", type="primary", use_container_width=True):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email_login, "password": password_login})
                    st.session_state.user = res.user
                    st.rerun()
                except Exception as e: st.error("Login failed. Check your credentials.")

    with tab_signup:
        with st.form("signup_form"):
            email_signup = st.text_input("Email (New Account)")
            password_signup = st.text_input("Password (New Account)", type="password")
            if st.form_submit_button("Sign Up", type="primary", use_container_width=True):
                try:
                    res = supabase.auth.sign_up({"email": email_signup, "password": password_signup})
                    st.session_state.user = res.user
                    st.rerun()
                except Exception as e: st.error(f"Signup failed: {e}")

# --- MAIN APPLICATION SCREEN ---
else:
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("Log Out"):
            supabase.auth.sign_out()
            st.session_state.user = None
            st.session_state.current_results = None
            st.rerun()
            
    # THE 3-TAB NAVIGATION
    tab_explore, tab_profile, tab_saved = st.tabs(["🌍 Explore", "👤 My Profile", "⭐ Saved Spots"])

    # ----------------------------------------
    # TAB 1: EXPLORE
    # ----------------------------------------
    with tab_explore:
        user_profile = get_profile(st.session_state.user.id)
        
        st.subheader("Where are we going?")
        loc_col1, loc_col2 = st.columns([5, 1])
        with loc_col1: location_input = st.text_input("Location", placeholder="Enter City or ZIP Code (e.g., Fairfax, VA)", label_visibility="collapsed")
        with loc_col2: geo_data = streamlit_geolocation()

        gps_active = False
        if geo_data and geo_data.get('latitude') is not None:
            gps_active = True
            st.success("🌿 GPS Locked!")

        st.write("---")
        st.subheader("What's the plan?")

        col_day, col_time = st.columns(2)
        with col_day: day_choice = st.radio("Day", ["☀️ Today", "📅 Tomorrow"], horizontal=True, label_visibility="collapsed")
        with col_time: time_choice = st.radio("Time", ["☀️ Daytime", "🌙 Night"], horizontal=True, label_visibility="collapsed")
        intended_time = f"{day_choice} ({time_choice})"

        st.write("") 
        col_group, col_vibe = st.columns(2)
        with col_group: group_type = st.selectbox("Who is going?", ["Date", "Family Outing", "Friends", "Solo"])
        with col_vibe: vibe = st.radio("Setting?", ["Doesn't Matter", "Outside", "Inside"], horizontal=True)
        
        st.write("") 
        col_food, col_dist = st.columns(2)
        with col_food: food_pref = st.selectbox("Sustenance?", ["Full Meal", "Just Drinks/Coffee", "No Food Needed"])
        with col_dist: distance = st.slider("Max Distance (Miles)", 1, 20, 5)

        with st.expander("Need something specific? (Optional)", expanded=False):
            specific_request = st.text_input("Keyword", placeholder="e.g., 'live jazz', 'vegan options'", label_visibility="collapsed")

        filters_dict = {"group": group_type, "time": intended_time, "vibe": vibe, "food": food_pref, "specific": specific_request}

        st.write("---")
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1: top_3_clicked = st.button("🌟 Top 3 Recommendations", use_container_width=True)
        with btn_col2: get_wild_clicked = st.button("🎲 GET WILD", type="primary", use_container_width=True)

        # Execution Logic
        if top_3_clicked or get_wild_clicked:
            mode = "get_wild" if get_wild_clicked else "top_3"
            if not location_input and not gps_active:
                st.warning("Please enter a location or click the GPS icon first!")
            else:
                with st.spinner("Scouting the wild..."):
                    try:
                        current_date = datetime.now().strftime("%A, %B %d, %Y")
                        location_context = location_input
                        if gps_active:
                            lat, lng = geo_data['latitude'], geo_data['longitude']
                            location_context = "exact GPS coordinates"
                        else:
                            lat, lng = get_coordinates(location_input)
                        
                        if lat is None: st.error("Couldn't find that location.")
                        else:
                            semantic_query = build_semantic_query(filters_dict, user_profile)
                            raw_places = fetch_places_semantic(semantic_query, lat, lng, distance)
                            live_events_data = fetch_live_events(location_input if location_input else "nearby", intended_time, group_type, current_date)
                            
                            st.session_state.current_results = get_ai_recommendations(raw_places, live_events_data, filters_dict, location_context, current_date, user_profile, mode=mode)
                            st.session_state.current_mode = mode
                    except Exception as e: st.error(f"Error: {e}")

        # Render Results
        if st.session_state.current_results:
            results = st.session_state.current_results
            mode = st.session_state.current_mode
            
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
                if st.button("🔖 Save to My List", key=f"save_wild_{spot['name']}"):
                    save_spot_to_db(st.session_state.user.id, spot['name'], spot['address'], spot.get('category', 'Spontaneous'))
                
            else:
                st.write("### Your Handpicked Spots:")
                for spot in results.get("recommendations", []):
                    with st.container():
                        st.markdown(f"<span style='color: #558b2f; font-weight: 700; text-transform: uppercase; font-size: 0.85rem; letter-spacing: 1px;'>{spot.get('category', 'Top Pick')}</span>", unsafe_allow_html=True)
                        st.subheader(spot['name'])
                        st.caption(f"📍 {spot['address']} | ✨ **{spot['vibe_check']}**")
                        st.write(spot['why_its_perfect'])
                        
                        btn_c1, btn_c2 = st.columns([3, 1])
                        with btn_c1:
                            search_term = spot['name'].replace(' ', '+') + f"+{location_input.replace(' ', '+')}"
                            map_url = f"https://www.google.com/maps/search/?api=1&query={search_term}"
                            st.markdown(f'<a href="{map_url}" target="_blank" class="take-me-there-btn" style="margin-top: 0;">Take me there!</a>', unsafe_allow_html=True)
                        with btn_c2:
                            if st.button("🔖 Save", key=f"save_{spot['name']}"):
                                save_spot_to_db(st.session_state.user.id, spot['name'], spot['address'], spot.get('category', 'Top Pick'))
                        st.write("---")

    # ----------------------------------------
    # TAB 2: MY PROFILE
    # ----------------------------------------
    with tab_profile:
        st.subheader("Personalize Your AI")
        st.write("Set your baseline preferences so the app learns how you like to explore.")
        
        current_prof = get_profile(st.session_state.user.id) or {}
        
        with st.form("profile_form"):
            fname = st.text_input("First Name", value=current_prof.get('first_name', ''))
            pname = st.text_input("Partner/Spouse Name (Optional)", value=current_prof.get('partner_name', ''))
            
            st.write("Accessibility & Pets:")
            stroller = st.checkbox("Require Stroller Accessibility", value=current_prof.get('needs_stroller_access', False))
            dog = st.checkbox("Require Dog-Friendly Patios (When 'Outside' is selected)", value=current_prof.get('needs_dog_friendly', False))
            
            st.write("Vibe Check:")
            vibe_pref = st.text_area("What is your ideal aesthetic? (e.g., 'Warm, modern, naturalistic, quiet')", value=current_prof.get('vibe_preference', ''))
            
            if st.form_submit_button("Save Profile", type="primary"):
                supabase.table('user_profiles').upsert({
                    'id': st.session_state.user.id,
                    'first_name': fname,
                    'partner_name': pname,
                    'needs_stroller_access': stroller,
                    'needs_dog_friendly': dog,
                    'vibe_preference': vibe_pref
                }).execute()
                st.success("Profile updated! The AI will now use these rules.")

    # ----------------------------------------
    # TAB 3: SAVED SPOTS
    # ----------------------------------------
    with tab_saved:
        st.subheader("Your Adventure Ledger")
        st.write("Rate your past spots. 5-star ratings will train the AI to find similar vibes!")
        
        res = supabase.table('saved_spots').select('*').eq('user_id', st.session_state.user.id).order('saved_at', desc=True).execute()
        saved_spots = res.data if res.data else []
        
        if not saved_spots:
            st.info("You haven't saved any spots yet. Go explore!")
        else:
            for saved in saved_spots:
                with st.expander(f"📍 {saved['spot_name']}"):
                    st.caption(saved['address'])
                    
                    with st.form(f"rate_form_{saved['id']}"):
                        current_rating = saved['rating'] if saved['rating'] else 3
                        new_rating = st.slider("Rate this spot (1-5 Stars)", 1, 5, current_rating)
                        notes = st.text_input("Private Notes", value=saved.get('user_notes', ''))
                        
                        if st.form_submit_button("Update Feedback"):
                            supabase.table('saved_spots').update({
                                'rating': new_rating,
                                'user_notes': notes
                            }).eq('id', saved['id']).execute()
                            st.success("Feedback saved!")