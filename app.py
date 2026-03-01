import streamlit as st
import requests
import json
import urllib.parse
import asyncio
import pandas as pd
from openai import OpenAI
from datetime import datetime
from streamlit_geolocation import streamlit_geolocation
from supabase import create_client, Client
from tenacity import retry, wait_exponential, stop_after_attempt

# ==========================================
# 1. CONFIGURATION & SECRETS
# ==========================================
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]
OPENWEATHER_API_KEY = st.secrets["OPENWEATHER_API_KEY"] 
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
    .wild-card { background: #ffffff; border: 1px solid #e0e0e0; border-radius: 16px; overflow: hidden; margin-top: 20px; margin-bottom: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.06); animation: fadeSlideUp 0.8s ease-out forwards; opacity: 0; transform: translateY(20px); }
    .wild-card-img { width: 100%; height: 220px; object-fit: cover; }
    .wild-card-content { padding: 20px; }
    .spot-category { color: #558b2f; font-weight: 700; text-transform: uppercase; font-size: 0.8rem; letter-spacing: 1px; margin-bottom: 5px; display: block; }
    .spot-title { font-size: 1.5rem; font-weight: 700; color: #1a1a1a; margin-top: 0; margin-bottom: 5px; }
    .spot-meta { font-size: 0.9rem; color: #666; margin-bottom: 15px; }
    .spot-pitch { font-size: 1.05rem; line-height: 1.5; color: #333; margin-bottom: 20px; }
    .link-row { display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }
    .outbound-link { background-color: #f5f5f5; color: #333 !important; padding: 8px 16px; border-radius: 20px; text-decoration: none; font-size: 0.9rem; font-weight: 600; border: 1px solid #e0e0e0; transition: all 0.2s; }
    .outbound-link:hover { background-color: #e0e0e0; }
    .uber-link { background-color: #000000; color: #ffffff !important; border-color: #000000; }
    .uber-link:hover { background-color: #333333; }
    .group-chat-box { font-family: monospace; background: #f8f9fa; padding: 15px; border-radius: 8px; border: 1px solid #ddd; }
    @keyframes fadeSlideUp { to { opacity: 1; transform: translateY(0); } }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# ==========================================
# 3. SESSION STATE & DATABASE HELPERS
# ==========================================
if 'user' not in st.session_state: st.session_state.user = None
if 'current_results' not in st.session_state: st.session_state.current_results = None 
if 'current_mode' not in st.session_state: st.session_state.current_mode = None
if 'session_seen_spots' not in st.session_state: st.session_state.session_seen_spots = [] # Tracks spots seen this session for the Shuffle feature

def get_profile(user_id):
    try:
        res = supabase.table('user_profiles').select('*').eq('id', user_id).execute()
        return res.data[0] if res.data else None
    except: return None

def get_excluded_spots(user_id):
    """Pulls ALL saved spots for this user so they are never recommended again."""
    try:
        res = supabase.table('saved_spots').select('spot_name').eq('user_id', user_id).execute()
        return [spot['spot_name'] for spot in res.data] if res.data else []
    except: return []

def save_spot_to_db(user_id, name, address, category, rating=None, notes=""):
    try:
        supabase.table('saved_spots').insert({
            'user_id': user_id, 'spot_name': name, 'address': address, 'category': category, 'rating': rating, 'user_notes': notes
        }).execute()
        
        if rating != 1:
            prof = get_profile(user_id)
            new_tally = (prof.get('wild_tally') or 0) + 1
            supabase.table('user_profiles').update({'wild_tally': new_tally}).eq('id', user_id).execute()
            st.toast(f"✅ Saved! Your Get Wild Tally is now {new_tally} 🏆")
        else:
            st.toast("🚫 Blacklisted. We won't recommend this again.")
    except Exception as e: st.error("Database error.")

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

def get_live_weather(lat, lng):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lng}&units=imperial&appid={OPENWEATHER_API_KEY}"
        res = requests.get(url).json()
        if res.get("cod") == 200:
            return f"{res['main']['temp']}°F and {res['weather'][0]['description']}"
        return "Weather data unavailable."
    except:
        return "Weather service currently unreachable."

def build_semantic_query(filters_dict, profile):
    modifiers = []
    if filters_dict['group'] == "Date": modifiers.append("romantic")
    elif filters_dict['group'] == "Family Outing": modifiers.append("kid-friendly")
    elif filters_dict['group'] == "Friends": modifiers.append("fun lively")
    elif filters_dict['group'] == "Solo": modifiers.append("cozy")

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

# SMART CACHING: Saves API calls & speeds up frequent searches
@st.cache_data(ttl=3600)
def fetch_places_semantic(semantic_query, lat, lng, radius_miles):
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        # Included places.location to power the interactive map
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.websiteUri,places.photos,places.editorialSummary,places.location"
    }
    radius_meters = int(radius_miles * 1609.34)
    data = {
        "textQuery": semantic_query,
        "pageSize": 20,
        "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_meters}}
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200: raise Exception(f"Google API Error: {response.text}")
    return response.json().get('places', [])

@st.cache_data(ttl=3600)
def fetch_live_events(location_name, intended_time, group_type, current_date):
    url = "https://api.tavily.com/search"
    query = f"Find specific local events, live music, festivals, trivia nights, or pop-ups happening on {intended_time} strictly in or near {location_name}. Today's date is {current_date}. List exact event names."
    payload = {"api_key": TAVILY_API_KEY, "query": query, "search_depth": "basic", "include_answer": True, "max_results": 3}
    try:
        response = requests.post(url, json=payload)
        data = response.json()
        return f"TAVILY AI WEB SEARCH SUMMARY: {data.get('answer', '')}"
    except: return "No live event data found."

@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
def get_ai_recommendations(raw_places, live_events_data, weather_report, filters_dict, location_name, current_date, profile, excluded_spots, mode="top_3"):
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    trimmed_places = raw_places[:8] if isinstance(raw_places, list) and len(raw_places) > 8 else raw_places
    safe_events_data = live_events_data[:4000] if isinstance(live_events_data, str) else live_events_data

    profile_context = ""
    if profile:
        stroller = "MUST be stroller accessible." if profile.get('needs_stroller_access') else ""
        dog = "MUST be dog-friendly." if profile.get('needs_dog_friendly') and filters_dict['vibe'] == "Outside" else ""
        vibe_pref = f"Prioritize locations matching this vibe: {profile.get('vibe_preference')}." if profile.get('vibe_preference') else ""
        profile_context = f"\nUSER BASELINE PROFILE:\n{stroller}\n{dog}\n{vibe_pref}"

    # SHUFFLE & SAVED EXCLUSION LOGIC
    blacklist_context = f"CRITICAL: DO NOT RECOMMEND ANY OF THESE PLACES: {', '.join(excluded_spots)}" if excluded_spots else ""

    instruction = """Select EXACTLY ONE option from the data. Assign it the category: 'Spontaneous Adventure'.""" if mode == "get_wild" else """Return EXACTLY 3 options from the data, structured strictly as:
        1. The Crowd-Pleaser: Established, highly-rated, local favorite.
        2. The Fresh Take / Live Event: You MUST heavily prioritize the 'LIVE WEB SEARCH EVENTS' data.
        3. The Hidden Gem: A spot that feels unique."""

    system_prompt = f"""
    You are a luxury local concierge for an app called 'Get Wild'.
    
    CRITICAL CONTEXT:
    - User Location: {location_name}
    - CURRENT WEATHER: {weather_report}
    - Today's Date: {current_date}
    - User Intended Time: {filters_dict['time']}
    - Session Profile: {filters_dict['group']} looking for {filters_dict['food']} in a {filters_dict['vibe']} setting.
    - SPECIAL REQUEST: "{filters_dict.get('specific') if filters_dict.get('specific') else 'None'}"
    {profile_context}
    {blacklist_context}
    
    GEOGRAPHY, WEATHER & HALLUCINATION SHACKLES:
    1. WEATHER PIVOT: If weather report indicates RAIN, SNOW, or TEMP < 45°F, prioritize indoor venues or those with heated patios.
    2. DO NOT INVENT PLACES. Must be in the provided data.
    3. STRICT GEOGRAPHY: Must be physically in or immediately bordering {location_name}.
    
    {instruction}
    
    Return STRICTLY as a JSON object with a 'recommendations' array containing:
    'name', 'category', 'address', 'why_its_perfect' (2 sentences), 'vibe_check' (3 words), 'website' (URL if available in data, otherwise empty string), 'photo_ref' (The string from places.photos[0].name if available, otherwise empty), 'lat' (float of latitude), and 'lng' (float of longitude). Provide approximate lat/lng for live events based on city.
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"GOOGLE PLACES DATA: {json.dumps(trimmed_places)}\n\nLIVE WEB SEARCH EVENTS:\n{safe_events_data}"}
        ],
        max_tokens=600  # Bumped slightly to account for mapping coordinates
    )
    return json.loads(response.choices[0].message.content)

def render_spot_card(spot, location_input, user_id):
    search_term = spot['name'].replace(' ', '+') + f"+{location_input.replace(' ', '+')}"
    map_url = f"https://www.google.com/maps/search/?api=1&query={search_term}"
    encoded_address = urllib.parse.quote(spot['address'])
    uber_url = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_address}"
    
    if spot.get('photo_ref'):
        img_url = f"https://places.googleapis.com/v1/{spot['photo_ref']}/media?key={GOOGLE_API_KEY}&maxHeightPx=400&maxWidthPx=800"
    else:
        text_to_check = f"{spot['name']} {spot.get('category', '')} {spot.get('why_its_perfect', '')}".lower()
        if "comedy" in text_to_check or "stand-up" in text_to_check or "laugh" in text_to_check:
            img_url = "https://images.unsplash.com/photo-1585699324551-f6c309eedeca?w=800&q=80" 
        elif "outdoor" in text_to_check or "amphitheater" in text_to_check or "festival" in text_to_check:
            img_url = "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=800&q=80" 
        elif "music" in text_to_check or "concert" in text_to_check or "jazz" in text_to_check or "band" in text_to_check:
            img_url = "https://images.unsplash.com/photo-1540039155732-d68a96670afb?w=800&q=80" 
        else:
            img_url = "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=800&q=80" 
            
    img_html = f'<img src="{img_url}" class="wild-card-img">'
    website_html = f'<a href="{spot["website"]}" target="_blank" class="outbound-link">🌐 Website</a>' if spot.get('website') else ""

    html_card = f"""
<div class="wild-card">
{img_html}
<div class="wild-card-content">
<span class="spot-category">{spot.get('category', 'Top Pick')}</span>
<h2 class="spot-title">{spot['name']}</h2>
<div class="spot-meta">📍 {spot['address']} | ✨ <b>{spot['vibe_check']}</b></div>
<p class="spot-pitch">{spot['why_its_perfect']}</p>
<div class="link-row">
<a href="{map_url}" target="_blank" class="outbound-link">🗺️ Maps</a>
{website_html}
<a href="{uber_url}" target="_blank" class="outbound-link uber-link">🚗 Ride with Uber</a>
</div>
</div>
</div>
"""
    st.markdown(html_card, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("🔖 Save to List", key=f"save_{spot['name']}"):
            save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'))
    with col2:
        if st.button("🚫 Not for me", key=f"hate_{spot['name']}"):
            save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'), rating=1, notes="Blacklisted via quick-button.")

# ==========================================
# 5. ASYNC DATA GATHERER 
# ==========================================
async def gather_all_data(lat, lng, semantic_query, distance, location_input, intended_time, group_type, current_date):
    """Runs the API calls in parallel background threads to slash load times."""
    weather_task = asyncio.to_thread(get_live_weather, lat, lng)
    places_task = asyncio.to_thread(fetch_places_semantic, semantic_query, lat, lng, distance)
    events_task = asyncio.to_thread(fetch_live_events, location_input if location_input else "nearby", intended_time, group_type, current_date)
    return await asyncio.gather(weather_task, places_task, events_task)

# ==========================================
# 6. UI ROUTING
# ==========================================
st.markdown("""
<div class="hero-header">
    <h1 class="hero-title">Get Wild</h1>
    <p class="hero-subtitle">Disconnect. Explore. Connect.</p>
</div>
""", unsafe_allow_html=True)

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

else:
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("Log Out"):
            supabase.auth.sign_out()
            st.session_state.user = None
            st.session_state.current_results = None
            st.session_state.session_seen_spots = []
            st.rerun()
            
    tab_explore, tab_profile, tab_saved = st.tabs(["🌍 Explore", "👤 My Profile", "⭐ Saved Spots"])

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
        
        # UI: Add Shuffle Button
        btn_col1, btn_col2, btn_col3 = st.columns(3)
        with btn_col1: top_3_clicked = st.button("🌟 Top 3 Recommendations", use_container_width=True)
        with btn_col2: get_wild_clicked = st.button("🎲 GET WILD", type="primary", use_container_width=True)
        with btn_col3: shuffle_clicked = st.button("🔀 Shuffle Options", use_container_width=True)

        if top_3_clicked or get_wild_clicked or shuffle_clicked:
            if shuffle_clicked and not st.session_state.session_seen_spots:
                st.warning("Nothing to shuffle yet! Start by finding your first spots.")
            else:
                mode = "get_wild" if get_wild_clicked or (shuffle_clicked and st.session_state.current_mode == "get_wild") else "top_3"
                if not location_input and not gps_active:
                    st.warning("Please enter a location or click the GPS icon first!")
                else:
                    # Dynamic Status Loader instead of static spinner
                    with st.status("Scouting the wild...", expanded=True) as status:
                        try:
                            current_date = datetime.now().strftime("%A, %B %d, %Y")
                            location_context = location_input
                            
                            st.write("📍 Getting coordinates...")
                            if gps_active:
                                lat, lng = geo_data['latitude'], geo_data['longitude']
                                location_context = "exact GPS coordinates"
                            else:
                                lat, lng = get_coordinates(location_input)
                            
                            if lat is None: 
                                st.error("Couldn't find that location.")
                                status.update(label="Location Error", state="error")
                            else:
                                st.write("☁️ Fetching live weather, places, and local events...")
                                semantic_query = build_semantic_query(filters_dict, user_profile)
                                
                                # Parallel processing via Asyncio
                                weather_report, raw_places, live_events_data = asyncio.run(
                                    gather_all_data(lat, lng, semantic_query, distance, location_input, intended_time, group_type, current_date)
                                )
                                
                                st.write("🧠 The AI is assembling your perfect itinerary...")
                                
                                # EXCLUSION LOGIC: Combine DB Saved Spots + Spots seen this session (Shuffle)
                                db_excluded = get_excluded_spots(st.session_state.user.id)
                                all_excluded = list(set(db_excluded + st.session_state.session_seen_spots))
                                
                                st.session_state.current_results = get_ai_recommendations(raw_places, live_events_data, weather_report, filters_dict, location_context, current_date, user_profile, all_excluded, mode=mode)
                                st.session_state.current_mode = mode
                                
                                # Track these new spots so they aren't repeated on the next shuffle
                                for rec in st.session_state.current_results.get("recommendations", []):
                                    st.session_state.session_seen_spots.append(rec['name'])

                                status.update(label="Itinerary Ready!", state="complete", expanded=False)
                        except Exception as e: 
                            st.error(f"Error: {e}")
                            status.update(label="An error occurred", state="error")

        if st.session_state.current_results:
            st.write("---")
            results = st.session_state.current_results
            
            # --- INTERACTIVE MAP ---
            map_data = []
            for spot in results.get("recommendations", []):
                if spot.get('lat') and spot.get('lng'):
                    map_data.append({"lat": spot['lat'], "lon": spot['lng'], "name": spot['name']})
            
            if map_data:
                st.subheader("🗺️ Your Night at a Glance")
                st.map(pd.DataFrame(map_data), zoom=12)
                st.write("")
            
            # --- RENDER CARDS ---
            chat_text = "Hey! Check out this plan I made on Get Wild:\n\n"
            
            for index, spot in enumerate(results.get("recommendations", [])):
                render_spot_card(spot, location_input, st.session_state.user.id)
                st.write("---")
                
                # Build Group Chat String
                chat_text += f"{index + 1}. {spot['name']} - {spot['vibe_check']}\n"
                chat_text += f"📍 {spot['address']}\n"
                chat_text += f"🗺️ https://www.google.com/maps/search/?api=1&query={spot['name'].replace(' ', '+')}+{urllib.parse.quote(location_input)}\n\n"
            
            # --- THE VIRAL LOOP (SEND TO GROUP CHAT) ---
            st.subheader("💬 Send to the Group Chat")
            st.text_area("Copy and paste this into iMessage or WhatsApp:", value=chat_text.strip(), height=200)

    # ----------------------------------------
    # TAB 2 & 3: PROFILE & SAVED SPOTS (Unchanged)
    # ----------------------------------------
    with tab_profile:
        current_prof = get_profile(st.session_state.user.id) or {}
        st.markdown(f"### 🏆 Get Wild Tally: **{current_prof.get('wild_tally', 0)}**")
        st.write("Save spots to increase your tally and build your exploration streak!")
        st.write("---")
        st.subheader("Personalize Your AI")
        st.write("Set your baseline preferences so the app learns how you like to explore.")
        
        with st.form("profile_form"):
            fname = st.text_input("First Name", value=current_prof.get('first_name', ''))
            pname = st.text_input("Partner/Spouse Name (Optional)", value=current_prof.get('partner_name', ''))
            stroller = st.checkbox("Require Stroller Accessibility", value=current_prof.get('needs_stroller_access', False))
            dog = st.checkbox("Require Dog-Friendly Patios", value=current_prof.get('needs_dog_friendly', False))
            vibe_pref = st.text_area("What is your ideal aesthetic? (e.g., 'Warm, modern, naturalistic')", value=current_prof.get('vibe_preference', ''))
            
            if st.form_submit_button("Save Profile", type="primary"):
                supabase.table('user_profiles').upsert({
                    'id': st.session_state.user.id, 'first_name': fname, 'partner_name': pname,
                    'needs_stroller_access': stroller, 'needs_dog_friendly': dog, 'vibe_preference': vibe_pref
                }).execute()
                st.success("Profile updated! The AI will now use these rules.")

    with tab_saved:
        st.subheader("Your Adventure Ledger")
        st.write("Rate your past spots. Spots rated 1-star will NEVER be recommended again.")
        res = supabase.table('saved_spots').select('*').eq('user_id', st.session_state.user.id).order('saved_at', desc=True).execute()
        saved_spots = res.data if res.data else []
        
        if not saved_spots:
            st.info("You haven't saved any spots yet. Go explore!")
        else:
            for saved in saved_spots:
                icon = "🚫" if saved['rating'] == 1 else "📍"
                with st.expander(f"{icon} {saved['spot_name']}"):
                    st.caption(saved['address'])
                    with st.form(f"rate_form_{saved['id']}"):
                        current_rating = saved['rating'] if saved['rating'] else 3
                        new_rating = st.slider("Rate this spot (1-5 Stars. 1 = Blacklist)", 1, 5, current_rating)
                        notes = st.text_input("Private Notes", value=saved.get('user_notes', ''))
                        if st.form_submit_button("Update Feedback"):
                            supabase.table('saved_spots').update({'rating': new_rating, 'user_notes': notes}).eq('id', saved['id']).execute()
                            st.success("Feedback saved!")