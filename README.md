def main():
    try:
        # Ensure folders exist
        os.makedirs(input_folder, exist_ok=True)
        os.makedirs(output_folder, exist_ok=True)
        os.makedirs(history_folder, exist_ok=True)

        logging.info(f"Checking {input_folder} for .txt files...")

        files = [f for f in os.listdir(input_folder) if f.lower().endswith(".txt") 
                 and os.path.isfile(os.path.join(input_folder, f))]

        if not files:
            logging.info("No .txt files found in input folder. Exiting.")
            return  # Exit gracefully

        # Process only the first file found (or loop through all if needed)
        first_file = os.path.join(input_folder, files[0])
        process_file(first_file)

        logging.info("Run completed successfully. Exiting now.")

    except Exception as e:
        logging.error(f"Fatal error occurred: {e}", exc_info=True)
        raise SystemExit(1)  # Stop execution immediately


if __name__ == "__main__":
    main()