import streamlit as st
import requests
import json
from openai import OpenAI
from datetime import datetime
from streamlit_geolocation import streamlit_geolocation

# ==========================================
# 1. CONFIGURATION & SECRETS
# ==========================================
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"] # NEW: The Web Scraper Key

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
# 3. HELPER FUNCTIONS (The V3 Agentic Engine)
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
    
    if filters_dict['food'] == "Full Meal": base = "restaurants"
    elif filters_dict['food'] == "Just Drinks/Coffee": base = "bars, cafes, or breweries"
    else: base = "parks and outdoor activities" if filters_dict['vibe'] == "Outside" else "attractions and activities"
            
    query = f"{modifier_str} {base}".strip()
    if filters_dict['vibe'] == "Outside" and filters_dict['food'] in ["Full Meal", "Just Drinks/Coffee"]:
        query += " with outdoor seating"
        
    return query

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

# --- NEW: The Agentic Web Scraper ---
def fetch_live_events(location_name, intended_time, group_type):
    """Uses Tavily to scrape the web for local events happening at the intended time."""
    url = "https://api.tavily.com/search"
    query = f"What fun local events, live music, pop-ups, or specials are happening {intended_time} near {location_name} for a {group_type}?"
    
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
        # Returns a synthesized summary of the web search
        answer = data.get("answer", "")
        context = " ".join([res.get("content", "") for res in data.get("results", [])])
        return f"TAVILY AI WEB SEARCH SUMMARY: {answer} \n\nRAW WEB CONTEXT: {context}"
    except Exception as e:
        return "No live event data found on the web."

def get_ai_recommendations(raw_places, live_events_data, filters_dict, location_name, mode="top_3"):
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
        2. The Fresh Take / Live Event: You MUST use the 'LIVE WEB SEARCH EVENTS' data to recommend something happening *specifically* at the user's intended time (e.g., a trivia night, live band, or local festival). If the web search found nothing good, pick a trendy, experiential place from the Google data instead.
        3. The Hidden Gem: A spot that feels off the beaten path, unique, or known mostly to locals.
        """

    system_prompt = f"""
    You are a luxury local concierge for an app called 'Get Wild'.
    
    CRITICAL CONTEXT:
    - User Intended Time: {intended_time}
    - User Profile: {filters_dict['group']} looking for {filters_dict['food']} in a {filters_dict['vibe']} setting.
    - SPECIAL REQUEST: "{specific_request if specific_request else 'None'}"
    
    DATA SOURCES:
    1. GOOGLE PLACES DATA: A list of established local venues.
    2. LIVE WEB SEARCH EVENTS: Live data scraped from the web about things happening right now.
    
    SPECIAL REQUEST MANDATE:
    If a SPECIAL REQUEST is provided, it is your absolute highest priority. 
    
    ANTI-HALLUCINATION PROTOCOL:
    1. ONLY recommend places from the provided JSON or the Web Search data. Do not invent places or events.
    2. Severely penalize massive corporate chains.
    
    {instruction}
    
    Return STRICTLY as a JSON object with a 'recommendations' array containing:
    'name', 'category', 'address', 'why_its_perfect' (2 sentences proving why it fits their filters. If it's a live event, explicitly mention what the event is!), and 'vibe_check' (3 words).
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
# 4. STREAMLIT UI (The Frontend)
# ==========================================
st.markdown("""
<div class="hero-header">
    <h1 class="hero-title">Get Wild</h1>
    <p class="hero-subtitle">Disconnect. Explore. Breathe.</p>
</div>
""", unsafe_allow_html=True)

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
    day_toggle = st.radio("Day?", ["Today", "Tomorrow"], horizontal=True)
with col_time:
    time_toggle = st.radio("Time?", ["Daytime", "Night"], horizontal=True)

intended_time = f"{day_toggle} ({time_toggle})"
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

# ==========================================
# 5. EXECUTION LOGIC
# ==========================================
if top_3_clicked or get_wild_clicked:
    mode = "get_wild" if get_wild_clicked else "top_3"
    
    if get_wild_clicked:
        st.balloons()
    
    if not location_input and not gps_active:
        st.warning("Please enter a location or click the GPS icon first!")
    else:
        # Changed st.spinner to st.status for better progressive UX loading
        with st.status("Scouting the wild...", expanded=True) as status:
            try:
                location_context = location_input
                if gps_active:
                    lat, lng = geo_data['latitude'], geo_data['longitude']
                    location_context = "their exact GPS coordinates"
                else:
                    st.write("📍 Converting location to GPS...")
                    lat, lng = get_coordinates(location_input)
                
                if lat is None:
                    status.update(label="Location error", state="error")
                    st.error("Couldn't find that location.")
                else:
                    st.write("🏢 Checking local venues via Google...")
                    semantic_query = build_semantic_query(filters_dict)
                    raw_places = fetch_places_semantic(semantic_query, lat, lng, distance)
                    
                    st.write("🌍 Scanning the local web for live events...")
                    live_events_data = fetch_live_events(location_input if location_input else "nearby", intended_time, group_type)
                    
                    st.write("🧠 Curating your perfect outing...")
                    results = get_ai_recommendations(raw_places, live_events_data, filters_dict, location_context, mode=mode)
                    
                    status.update(label="Ready to go!", state="complete", expanded=False)
                    
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
                            
            except Exception as e:
                status.update(label="Error encountered", state="error")
                st.error(f"Whoops! Something went wrong out in the wild: {e}")