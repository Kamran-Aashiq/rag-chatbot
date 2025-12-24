import os
import base64

from dotenv import load_dotenv      
from langchain_openai import ChatOpenAI

# Use GPT-4 Vision model
vision_llm = ChatOpenAI(model="gpt-4o", temperature=0.7)  # gpt-4o has vision capabilities
LLM_AVAILABLE = vision_llm is not None
load_dotenv()

# Remove all OCR-related code and replace with this:

def encode_image(image_path):
    """Encode image to base64 for GPT Vision"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def process_image(file_path: str, question: str, chat_id: str, vision_llm, setup_db, save_message, get_conversation_history):
    """Use GPT Vision to read images and answer questions"""
    
    # Validate input file
    if not os.path.exists(file_path):
        raise RuntimeError(f"Image file not found: {file_path}")

    conn = None
    try:
        # Encode image to base64
        base64_image = encode_image(file_path)
        
        # Save user message and build history
        conn = setup_db()
        save_message(conn, chat_id, 'user', f"[image uploaded] {question}")
        history = get_conversation_history(conn, chat_id)

        # Create GPT Vision prompt
        prompt = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text", 
                        "text": f"""You are AquaAI, a water management and climate change expert. 
                        
Conversation history:
{history}

User question: {question}

Analyze this image and provide a helpful answer. Focus on water, climate, sustainability aspects if relevant."""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]

        # Query the LLM with vision capability
        try:
            # Use invoke for the vision model
            response = vision_llm.invoke(prompt)
            answer = response.content
        except Exception as e:
            raise RuntimeError(f"GPT Vision call failed: {e}")

        save_message(conn, chat_id, 'assistant', answer)
        
        return {"response": answer, "image_analysis": "Processed with GPT Vision"}

    except Exception:
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

# Set OCR_AVAILABLE to True since we're using GPT Vision instead
OCR_AVAILABLE = True