import streamlit as st
import requests
import json
from openai import OpenAI
from datetime import datetime
from streamlit_geolocation import streamlit_geolocation

# ==========================================
# 1. CONFIGURATION & SECRETS
# ==========================================
# Pulling securely from Streamlit Cloud Secrets
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

# ==========================================
# 2. HELPER FUNCTIONS (The Engine)
# ==========================================
def get_coordinates(location_query):
    """Converts a ZIP code or City into Latitude/Longitude using Google."""
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={location_query}&key={GOOGLE_API_KEY}"
    response = requests.get(url).json()
    
    if response['status'] == 'OK':
        location = response['results'][0]['geometry']['location']
        return location['lat'], location['lng']
    else:
        return None, None

def fetch_local_places(lat, lng, radius_miles):
    """Fetches raw data from Google Places API using dynamic coordinates."""
    radius_meters = int(radius_miles * 1609.34)
    url = "https://places.googleapis.com/v1/places:searchNearby"
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.types"
    }
    
    data = {
        "includedTypes": ["restaurant", "bar", "cafe", "park", "tourist_attraction", "museum", "bowling_alley"],
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius_meters
            }
        }
    }

    response = requests.post(url, headers=headers, json=data)
    return response.json().get('places', [])

def get_ai_recommendations(raw_places, user_filters, current_time, location_name, mode="top_3"):
    """Sends raw places, user filters, and the CURRENT TIME to the LLM."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    if mode == "get_wild":
        instruction = "Select EXACTLY ONE completely random, but highly-rated option that fits the criteria for a spontaneous adventure."
    else:
        instruction = "Select the absolute BEST 3 options that match the user's filters. Filter out tourist traps."

    system_prompt = f"""
    You are the expert curation engine for a local discovery app called 'Get Wild'.
    
    CRITICAL CONTEXT:
    - The user is searching near: {location_name}
    - The current local day and time is: {current_time}
    
    Using the time provided, DO NOT recommend places that are likely closed or have the wrong vibe for this time of day (e.g., no nightclubs at 9 AM, no breakfast cafes at 8 PM).
    
    {instruction}
    Return the result STRICTLY as a JSON object with a 'recommendations' array containing:
    'name', 'address', 'why_its_perfect' (2-sentence pitch factoring in the time/vibe), and 'vibe_check' (3-word summary).
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
# 3. STREAMLIT UI (The Frontend)
# ==========================================
st.set_page_config(page_title="Get Wild", page_icon="🔥", layout="centered")

st.title("🔥 Get Wild")
st.markdown("Skip the endless scrolling. Tell us your vibe, and we'll tell you where to go.")

# --- Filters Section ---
st.subheader("Where are we going?")

# This splits the layout so the text box is wide and the GPS button is small
loc_col1, loc_col2 = st.columns([5, 1])

with loc_col1:
    location_input = st.text_input("Enter City or ZIP Code", value="Fairfax, VA", label_visibility="collapsed")

with loc_col2:
    # This creates the clickable GPS crosshairs icon
    geo_data = streamlit_geolocation()

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
    top_3_clicked = st.button("🌟 Get Top 3 Recommendations", use_container_width=True)

with btn_col2:
    get_wild_clicked = st.button("GET WILD", type="primary", use_container_width=True)

# ==========================================
# 4. EXECUTION LOGIC
# ==========================================
if top_3_clicked or get_wild_clicked:
    mode = "get_wild" if get_wild_clicked else "top_3"
    
    if get_wild_clicked:
        st.balloons() 
    
    with st.spinner("Scouting the best spots..."):
        try:
            # Determine Location (GPS overrides text input if clicked)
            lat, lng = None, None
            location_context = location_input
            
            if geo_data and geo_data.get('latitude') is not None and geo_data.get('longitude') is not None:
                lat = geo_data['latitude']
                lng = geo_data['longitude']
                location_context = "their exact GPS coordinates"
            elif location_input:
                lat, lng = get_coordinates(location_input)
            
            if lat is None:
                st.error("Couldn't find that location. Try a different ZIP code or click the GPS icon.")
            else:
                current_time_str = datetime.now().strftime("%A, %I:%M %p")
                
                raw_places = fetch_local_places(lat=lat, lng=lng, radius_miles=distance)
                results = get_ai_recommendations(raw_places, current_filters, current_time_str, location_context, mode=mode)
                
                st.write("### Your Handpicked Spots:" if mode == "top_3" else "### Your Spontaneous Adventure:")
                
                for spot in results.get("recommendations", []):
                    with st.container():
                        st.subheader(spot['name'])
                        st.caption(f"📍 {spot['address']} | ✨ **{spot['vibe_check']}**")
                        st.write(spot['why_its_perfect'])
                        
                        # Build Maps URL
                        search_term = spot['name'].replace(' ', '+')
                        if not (geo_data and geo_data.get('latitude')):
                            search_term += f"+{location_input.replace(' ', '+')}"
                            
                        map_url = f"https://www.google.com/maps/search/?api=1&query={search_term}"
                        st.markdown(f"[Take me there!]({map_url})")
                        st.write("---")
                        
        except Exception as e:
            st.error(f"Whoops! Something went wrong out in the wild: {e}")