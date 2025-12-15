import json
from flask import request, jsonify

@api_bp.route('/github_workflow', methods=['POST'])
def github_workflow():
    try:
        data = request.get_json()

        # Convert dimensions string → JSON
        if "dimensions" in data and isinstance(data["dimensions"], str):
            data["dimensions"] = json.loads(data["dimensions"])

        return jsonify(data), 200

    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        return jsonify({
            "success": False,
            "error": "An internal error occurred"
        }), 500