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
# This hides the default Streamlit header and injects our custom UI
st.set_page_config(page_title="Get Wild", page_icon="🌿", layout="centered")

custom_css = """
<style>
    /* Custom Title Area */
    .hero-header {
        text-align: center;
        padding: 2rem 0 1rem 0;
    }
    .hero-title {
        color: #2e7d32;
        font-family: 'Helvetica Neue', sans-serif;
        font-size: 3.5rem;
        font-weight: 800;
        letter-spacing: -1px;
        text-transform: uppercase;
        margin-bottom: 0;
        line-height: 1.1;
    }
    .hero-subtitle {
        color: #558b2f;
        font-size: 1.2rem;
        font-weight: 400;
        letter-spacing: 1px;
        margin-top: 10px;
    }
    
    /* Sleek CTA Button */
    .take-me-there-btn {
        display: inline-block;
        background-color: #2e7d32;
        color: white !important;
        text-align: center;
        padding: 12px 24px;
        border-radius: 8px;
        text-decoration: none;
        font-weight: 600;
        letter-spacing: 0.5px;
        width: 100%;
        transition: all 0.3s ease;
        margin-top: 10px;
    }
    .take-me-there-btn:hover {
        background-color: #1b5e20;
        box-shadow: 0 4px 12px rgba(46, 125, 50, 0.3);
    }

    /* The 'Get Wild' Special Reveal Card */
    .wild-card {
        background: linear-gradient(135deg, #f1f8e9 0%, #dcedc8 100%);
        border-left: 6px solid #558b2f;
        border-radius: 12px;
        padding: 25px;
        margin-top: 20px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.08);
        animation: fadeSlideUp 0.8s ease-out forwards;
        opacity: 0;
        transform: translateY(20px);
    }
    
    @keyframes fadeSlideUp {
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# ==========================================
# 3. HELPER FUNCTIONS (The Engine)
# ==========================================
def get_coordinates(location_query):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={location_query}&key={GOOGLE_API_KEY}"
    response = requests.get(url).json()
    if response['status'] == 'OK':
        loc = response['results'][0]['geometry']['location']
        return loc['lat'], loc['lng']
    return None, None

def fetch_local_places(lat, lng, radius_miles):
    radius_meters = int(radius_miles * 1609.34)
    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.types"
    }
    data = {
        "includedTypes": ["restaurant", "bar", "cafe", "park", "tourist_attraction", "museum", "bowling_alley", "hiking_area"],
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_meters}
        }
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json().get('places', [])

def get_ai_recommendations(raw_places, user_filters, current_time, location_name, mode="top_3"):
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    if mode == "get_wild":
        instruction = """
        Select EXACTLY ONE highly-rated option that fits the criteria for a spontaneous adventure.
        Make it something unexpected but perfectly matched to the user's filters.
        Assign it the category: "Spontaneous Adventure".
        """
    else:
        instruction = """
        You must return EXACTLY 3 options, strictly following this architectural structure:
        1. The Crowd-Pleaser: An established, highly-rated, popular, and "safe" choice.
        2. The Fresh Take: Something newer, trending, or event-driven (like a spot known for live music, trivia, or a modern menu).
        3. The Hidden Gem: Something completely off the beaten path, unique, or unexpected.
        
        Assign the exact category name to each option in your JSON response.
        """

    system_prompt = f"""
    You are the expert curation engine for a local discovery app called 'Get Wild'.
    
    CRITICAL CONTEXT:
    - Searching near: {location_name}
    - Current local time: {current_time}
    
    STRICT FILTER ADHERENCE RULES (DO NOT FAIL THESE):
    You must ruthlessly apply the user's filters: {user_filters}
    - IF 'Outside' is selected: The location MUST have a primary outdoor focus. If it's a restaurant, it MUST be renowned for a large patio, rooftop, or significant outdoor seating (like a brewery or winery). Do not recommend standard indoor restaurants.
    - IF 'Outside' AND 'Food' (Full Meal/Drinks) are selected: Do NOT recommend an empty park. You must recommend a dining establishment with significant outdoor space, or a park/venue that is explicitly known for having food trucks or heavy concessions.
    - IF 'Inside' is selected: Do not recommend parks, trails, or fully outdoor venues.
    
    Using the time provided, DO NOT recommend places that are likely closed or have the wrong vibe for this time of day.
    
    {instruction}
    
    Return the result STRICTLY as a JSON object with a 'recommendations' array. 
    Each item MUST contain:
    'name', 'category' (e.g., The Crowd-Pleaser), 'address', 'why_its_perfect' (2-sentence pitch EXPLAINING how it fits the filters and its specific category), and 'vibe_check' (3-word summary).
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"FILTERS: {user_filters}\nAVAILABLE PLACES: {json.dumps(raw_places)}"}
        ]
    )
    return json.loads(response.choices[0].message.content)

# ==========================================
# 4. STREAMLIT UI (The Frontend)
# ==========================================
# Custom Header Injection
st.markdown("""
<div class="hero-header">
    <h1 class="hero-title">Get Wild</h1>
    <p class="hero-subtitle">Disconnect. Explore. Breathe.</p>
</div>
""", unsafe_allow_html=True)

st.write("---")

# --- Filters Section ---
st.subheader("Where are we going?")

# Location Inputs
loc_col1, loc_col2 = st.columns([5, 1])

with loc_col1:
    # Changed from 'value' to 'placeholder' for better UX
    location_input = st.text_input("Location", placeholder="Enter City or ZIP Code (e.g., Fairfax, VA)", label_visibility="collapsed")

with loc_col2:
    geo_data = streamlit_geolocation()

# Real-time UI feedback for GPS
gps_active = False
if geo_data and geo_data.get('latitude') is not None:
    gps_active = True
    st.success("🌿 GPS Location Locked!")

st.write("---")
st.subheader("What's the plan?")
col1, col2 = st.columns(2)

with col1:
    group_type = st.selectbox("Who is going?", ["Date", "Family Outing", "Friends", "Solo"])
    vibe = st.radio("Inside or Outside?", ["Doesn't Matter", "Outside", "Inside"])

with col2:
    food_pref = st.selectbox("Sustenance?", ["Full Meal", "Just Drinks/Coffee", "No Food Needed"])
    cost = st.radio("Cost?", ["Any Price", "Free / Cheap", "Willing to Splurge"])

distance = st.slider("How far are you willing to travel? (Miles)", 1, 20, 5)
current_filters = f"{group_type}, {vibe}, {food_pref}, {cost}, within {distance} miles."

# --- Action Buttons ---
st.write("---")
btn_col1, btn_col2 = st.columns(2)

with btn_col1:
    top_3_clicked = st.button("🌟 Top 3 Recommendations", use_container_width=True)

with btn_col2:
    # Added the dice back to the button text
    get_wild_clicked = st.button("🎲 GET WILD", type="primary", use_container_width=True)

# ==========================================
# 5. EXECUTION LOGIC
# ==========================================
if top_3_clicked or get_wild_clicked:
    mode = "get_wild" if get_wild_clicked else "top_3"
    
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
                    current_time_str = datetime.now().strftime("%A, %I:%M %p")
                    raw_places = fetch_local_places(lat=lat, lng=lng, radius_miles=distance)
                    results = get_ai_recommendations(raw_places, current_filters, current_time_str, location_context, mode=mode)
                    
                    if mode == "get_wild":
                        # The Custom CSS Reveal Card for Get Wild
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
                                # Adds a sleek category label above the name
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