from flask import request, jsonify

@api_bp.route('/github_workflow', methods=['POST'])
def github_workflow():
    try:
        data = request.get_json()

        dimensions_raw = data.get("dimensions")

        # If dimensions was originally a string, it has already been converted
        # (based on your previous fix). Just return it.
        return jsonify(dimensions_raw), 200

    except Exception as e:
        logger.exception("Error processing chat message")
        return jsonify({
            "success": False,
            "error": "An internal error occurred"
        }), 500