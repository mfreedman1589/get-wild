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

# ==========================================
# 2. CUSTOM CSS & STYLING (The UX Layer)
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
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# ==========================================
# 3. HELPER FUNCTIONS (The Engine & Matrix)
# ==========================================
def get_coordinates(location_query):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={location_query}&key={GOOGLE_API_KEY}"
    response = requests.get(url).json()
    if response['status'] == 'OK':
        loc = response['results'][0]['geometry']['location']
        return loc['lat'], loc['lng']
    return None, None

def get_dynamic_place_types(food_pref, group_type, vibe):
    """THE MATRIX STEP 1: Dynamically changes what we ask Google for based on filters."""
    types = []
    
    if food_pref == "Full Meal":
        types.extend(["restaurant", "seafood_restaurant", "steak_house"])
    elif food_pref == "Just Drinks/Coffee":
        types.extend(["bar", "cafe", "coffee_shop", "brewery", "wine_bar"])
    elif food_pref == "No Food Needed":
        types.extend(["park", "museum", "tourist_attraction", "hiking_area", "bowling_alley", "movie_theater"])
        
    if group_type == "Family Outing":
        types.extend(["zoo", "aquarium", "amusement_park"])
        
    if vibe == "Outside":
        types.extend(["park", "brewery"]) # Breweries often have large outdoor spaces
        
    # Fallback to broad search if types is somehow empty
    if not types:
        types = ["restaurant", "bar", "park", "tourist_attraction"]
        
    # Remove duplicates and return
    return list(set(types))

def build_contextual_rules(group_type, intended_time, vibe, food_pref):
    """THE MATRIX STEP 2: Generates strict psychological rules for the AI."""
    rules = []
    is_night = "Night" in intended_time or "Tonight" in intended_time
    
    # 1. Who is going?
    if group_type == "Date":
        if is_night:
            rules.append("- DATE (NIGHT) MANDATE: Must be romantic, intimate, dimly lit, cozy, or an upscale experience. No loud sports bars or chaotic family venues.")
        else:
            rules.append("- DATE (DAY) MANDATE: Must be a cute, scenic, aesthetic, and relaxed environment for a daytime date.")
    elif group_type == "Family Outing":
        rules.append("- FAMILY MANDATE: Must be explicitly kid-friendly, safe, and family-welcoming. STRICTLY EXCLUDE rowdy bars, nightclubs, or 21+ only venues.")
    elif group_type == "Friends":
        rules.append("- FRIENDS MANDATE: Focus on lively, group-friendly, fun, or interactive spots with great energy (e.g., trivia, breweries, group seating).")
    elif group_type == "Solo":
        if vibe == "Outside" and is_night:
            rules.append("- SOLO (NIGHT/OUTSIDE) MANDATE: Focus on safe, comfortable-for-one spots like a sleek rooftop bar, a quiet patio, or an engaging solo experience.")
        else:
            rules.append("- SOLO MANDATE: Focus on spots welcoming to solo adventurers (e.g., bar seating, peaceful environments, or self-guided pacing).")
            
    # 2. Outdoor Enforcer
    if vibe == "Outside":
        if food_pref in ["Full Meal", "Just Drinks/Coffee"]:
            rules.append("- OUTDOOR DINING MANDATE: The venue MUST be renowned for its outdoor infrastructure (a sprawling patio, rooftop bar, waterfront view, or beer garden). Do NOT pick a standard indoor restaurant that just happens to have two sidewalk tables.")
        else:
            rules.append("- OUTDOOR MANDATE: Must be primarily an outdoor venue, park, or experience.")
            
    return "\n".join(rules)

def fetch_local_places(lat, lng, radius_miles, dynamic_types):
    radius_meters = int(radius_miles * 1609.34)
    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.types,places.regularOpeningHours"
    }
    data = {
        "includedTypes": dynamic_types,
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_meters}
        }
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json().get('places', [])

def get_ai_recommendations(raw_places, filters_dict, location_name, mode="top_3"):
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    group_type = filters_dict['group']
    intended_time = filters_dict['time']
    vibe = filters_dict['vibe']
    food_pref = filters_dict['food']
    
    # Inject the Matrix logic
    contextual_rules = build_contextual_rules(group_type, intended_time, vibe, food_pref)
    
    if mode == "get_wild":
        instruction = """
        Select EXACTLY ONE highly-rated option that fits the criteria for a spontaneous adventure.
        Make it something unexpected but perfectly matched to the user's filters.
        Assign it the category: "Spontaneous Adventure".
        """
    else:
        instruction = """
        You must return EXACTLY 3 options, strictly following this architectural structure:
        1. The Crowd-Pleaser: An established, highly-rated, popular, and "safe" choice matching the vibe.
        2. The Fresh Take / Live Event: Something newer, trending, or event-driven.
        3. The Hidden Gem (EXPERIENTIAL): Pick something truly off the beaten path or unique that actually exists in the data provided.
        
        Assign the exact category name to each option in your JSON response.
        """

    system_prompt = f"""
    You are the expert curation engine for a local discovery app called 'Get Wild'.
    
    CRITICAL CONTEXT:
    - Searching near: {location_name}
    - Intended Time: {intended_time}
    
    ANTI-HALLUCINATION PROTOCOL (MANDATORY):
    1. You MUST ONLY recommend real places from the 'AVAILABLE PLACES' JSON provided below. 
    2. DO NOT invent, combine, or hallucinate businesses. 
    3. If you cannot find a perfect "Hidden Gem" in the raw data, pick the most unique real option available. 
    
    TEMPORAL REALITY CHECK:
    - You must review the 'regularOpeningHours' provided in the JSON. 
    - If a venue closes before the user's Intended Time, you MUST NOT recommend it. 
    
    THE CONTEXTUAL MATRIX (STRICT ADHERENCE REQUIRED):
    {contextual_rules}
    
    {instruction}
    
    Return the result STRICTLY as a JSON object with a 'recommendations' array containing:
    'name', 'category', 'address', 'why_its_perfect' (2-sentence pitch EXPLAINING how it fits the Matrix rules), and 'vibe_check' (3-word summary).
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"AVAILABLE PLACES: {json.dumps(raw_places)}"}
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

# --- Filters Section ---
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

time_col, group_col = st.columns(2)
with time_col:
    intended_time = st.selectbox("When are we going?", ["Right Now", "Today (Daytime)", "Tonight", "Tomorrow Morning", "Tomorrow Night"])
with group_col:
    group_type = st.selectbox("Who is going?", ["Date", "Family Outing", "Friends", "Solo"])

vibe_col, food_col, cost_col = st.columns(3)
with vibe_col:
    vibe = st.radio("Setting?", ["Doesn't Matter", "Outside", "Inside"])
with food_col:
    food_pref = st.radio("Sustenance?", ["Full Meal", "Just Drinks/Coffee", "No Food Needed"])
with cost_col:
    cost = st.radio("Cost?", ["Any Price", "Free / Cheap", "Willing to Splurge"])

distance = st.slider("How far are you willing to travel? (Miles)", 1, 20, 5)

# Pack filters into a clean dictionary for the engine
filters_dict = {
    "group": group_type,
    "time": intended_time,
    "vibe": vibe,
    "food": food_pref,
    "cost": cost
}

# --- Action Buttons ---
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
        with st.spinner("Scouting the best spots..."):
            try:
                lat, lng = None, None
                location_context = location_input
                
                if gps_active:
                    lat, lng = geo_data['latitude'], geo_data['longitude']
                    location_context = "their exact GPS coordinates"
                elif location_input:
                    lat, lng = get_coordinates(location_input)
                
                if lat is None:
                    st.error("Couldn't find that location. Try a different ZIP code or City.")
                else:
                    # 1. Ask Matrix what Google Types to search for
                    dynamic_types = get_dynamic_place_types(food_pref, group_type, vibe)
                    
                    # 2. Fetch raw data from Google
                    raw_places = fetch_local_places(lat=lat, lng=lng, radius_miles=distance, dynamic_types=dynamic_types)
                    
                    # 3. Curate with AI using the Contextual Matrix Rules
                    results = get_ai_recommendations(raw_places, filters_dict, location_context, mode=mode)
                    
                    if mode == "get_wild":
                        spot = results.get("recommendations", [])[0]
                        search_term = spot['name'].replace(' ', '+')
                        if not gps_active:
                            search_term += f"+{location_input.replace(' ', '+')}"
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
                                
                                search_term = spot['name'].replace(' ', '+')
                                if not gps_active:
                                    search_term += f"+{location_input.replace(' ', '+')}"
                                map_url = f"https://www.google.com/maps/search/?api=1&query={search_term}"
                                
                                st.markdown(f'<a href="{map_url}" target="_blank" class="take-me-there-btn">Take me there!</a>', unsafe_allow_html=True)
                                st.write("---")
                            
            except Exception as e:
                st.error(f"Whoops! Something went wrong out in the wild: {e}")