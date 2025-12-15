from flask import request, jsonify

@api_bp.route('/github_workflow', methods=['POST'])
def github_workflow():
    try:
        data = request.get_json()

        dimensions_raw = data.get("dimensions")

        if isinstance(dimensions_raw, str):
            dimensions_raw = dimensions_raw.strip("{}")
            dimensions = {}

            for item in dimensions_raw.split(","):
                if "=" in item:
                    key, value = item.split("=", 1)
                    dimensions[key.strip()] = value.strip()

            data["dimensions"] = dimensions

        return jsonify(data), 200

    except Exception as e:
        logger.exception("Error processing chat message")
        return jsonify({
            "success": False,
            "error": "An internal error occurred"
        }), 500