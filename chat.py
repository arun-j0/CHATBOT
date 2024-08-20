import os
import re
import requests
import streamlit as st
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables from the .env file
load_dotenv()

# Retrieve API keys from environment variables
groq_api_key = os.getenv('GROQ_API_KEY')
youtube_api_key = os.getenv('YOUTUBE_API_KEY1')

# Function to interact with Groq API for chat completions
def get_chat_completion(message):
    api_url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama3-8b-8192",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant who helps users learn Python. Provide the required information to get the best results. Provide them in points so that users can understand better. Try to finish the response within 400 words. Avoid using complex words and jargon. Avoid providing responses that are incomplete."},
            {"role": "user", "content": message}
        ],
        "max_tokens": 400,
        "temperature": 0.7
    }
    
    response = requests.post(api_url, json=payload, headers=headers)
    
    if response.status_code == 200:
        chat_completion = response.json()
        return chat_completion["choices"][0]["message"]["content"]
    else:
        return f"Error: {response.status_code} - {response.json()}"

# Function to initialize YouTube API client
def get_youtube_service(api_key):
    return build('youtube', 'v3', developerKey=api_key)

# Function to check if the text is primarily in English
def is_english(text):
    # Patterns to identify non-English text
    non_english_patterns = [r'\b(?:Hindi|Chinese|French|German|Spanish|Japanese|Korean|Russian)\b',  # Add more languages as needed
                            r'[^\x00-\x7F]+']  # Matches non-ASCII characters
    return not any(re.search(pattern, text, re.IGNORECASE) for pattern in non_english_patterns)

# Function to search for YouTube videos related to a topic
def search_videos(youtube, topic, max_results=2, language='en'):
    try:
        request = youtube.search().list(
            part='snippet',
            q=topic,
            type='video',
            order='relevance',
            maxResults=max_results,
            relevanceLanguage=language  # Filter by language
        )
        response = request.execute()

        video_details = []
        for item in response.get('items', []):
            video_id = item['id']['videoId']
            video_title = item['snippet']['title']
            video_description = item['snippet']['description']
            
            # Filter out non-English videos
            if not is_english(video_title) or not is_english(video_description):
                continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            channel_title = item['snippet']['channelTitle']
            published_at = item['snippet']['publishedAt']
            video_details.append({
                'video_id': video_id,
                'title': video_title,
                'url': video_url,
                'channel_title': channel_title,
                'published_at': published_at
            })

        return video_details

    except HttpError as error:
        return f"An HTTP error occurred: {error}"

# Function to get video statistics from YouTube
def get_video_details(youtube, video_id):
    request = youtube.videos().list(
        part='statistics',
        id=video_id
    )
    response = request.execute()
    stats = response['items'][0]['statistics']
    return {
        'views': int(stats['viewCount']),
        'likes': int(stats.get('likeCount', 0)),
        'comments': int(stats.get('commentCount', 0))
    }

# Function to calculate relevance score of video title
def calculate_title_relevance_score(title, topic):
    return 1.0 if topic.lower() in title.lower() else 0.0

# Function to calculate video rating based on various metrics
def calculate_rating(video_details, title_relevance_score):
    views = video_details['views']
    likes = video_details['likes']
    comments = video_details['comments']

    # Normalize views and comments
    normalized_views = views / 1_000_000
    normalized_comments = comments / 1_000

    # Compute the rating based on relevance and engagement
    rating = (0.6 * title_relevance_score) + (0.2 * (likes / (views + 1))) + (0.1 * normalized_views) + (0.2 * normalized_comments)
    return round(min(rating * 10, 10), 1)

# Function to find top-rated videos for given topics
def find_top_rated_videos(api_key, topics):
    youtube = get_youtube_service(api_key)
    all_results = {}

    for topic in topics:
        videos = search_videos(youtube, topic)
        if isinstance(videos, str):
            return videos  # Return the error message if an error occurred
        
        results = []
        for video in videos:
            video_id = video['video_id']
            video_details = get_video_details(youtube, video_id)
            
            title_relevance_score = calculate_title_relevance_score(video['title'], topic)
            
            # Consider videos with at least 50 comments for rating
            if video_details['comments'] >= 50:
                rating = calculate_rating(video_details, title_relevance_score)
                
                results.append({
                    'title': video['title'],
                    'channel_name': video['channel_title'],
                    'date_uploaded': video['published_at'],
                    'rating': rating,
                    'url': video['url'],
                    'video_id': video['video_id']
                })
        
        results.sort(key=lambda x: x['rating'], reverse=True)
        all_results[topic] = results[:1]  # Get top 1 video for each topic
    
    return all_results

# Streamlit App Layout
st.title("Python Learning Chatbot")

# User input for Python question
user_input = st.text_input("Ask your Python question:")

# Handle user question submission
if st.button("Send"):
    if user_input:
        bot_response = get_chat_completion(user_input)
        st.write("**Bot Response:**")
        st.write(bot_response)
    else:
        st.write("Please enter a question.")

# Show tutorial button
if st.button("Facing difficulties? Watch some tutorial"):
    if user_input:
        # Parse user query into concepts
        # Split the user query on commas, "and", and "or" with optional whitespace
        concepts = [concept.strip()+" in Python" for concept in re.split(r'\s*,\s*|\s+and\s+|\s+or\s+', user_input)]
        
        # Add "in Python" to single-word concepts
        final_concepts = [concept + " in Python" if len(concept.split()) == 1 else concept for concept in concepts]
        
        top_videos = find_top_rated_videos(youtube_api_key, final_concepts)
        
        if isinstance(top_videos, str):
            st.error(top_videos)
        else:
            for concept, videos in top_videos.items():
                st.write(f"**Tutorials for '{concept}':**")
                for video in videos:
                    st.write(f"**{video['title']}**")
                    st.write(f"Channel: {video['channel_name']}")
                    st.write(f"Uploaded on: {video['date_uploaded']}")
                    st.write(f"[Watch Video]({video['url']})")
                    st.video(video['url'])
    else:
        st.write("Please enter a question to find a tutorial.")
