#!/usr/bin/env python3
"""
TV Series Thumbnail Generator

Automatically generates index.jpg thumbnails for TV series folders using TVMaze API (free, no key required).
Notifies the user about placing index.jpg files in folder subdirectories.

Usage:
    python generate_tv_thumbnails.py --target-dir "D:\TV\Detective,Thriller"
    python generate_tv_thumbnails.py --target-dir "D:\TV\Cartoon" --dry-run
"""

import argparse
import os
import re
import sys
import time
import requests
from PIL import Image
from io import BytesIO
import urllib.parse


# Folder filtering configuration
SKIP_FOLDERS = [
    '!Web Series',  # Exact matches to skip
    # Add more folders to skip below
]

def should_skip_folder(folder_name):
    """Check if folder should be skipped during thumbnail generation."""
    # Skip exact matches from SKIP_FOLDERS
    if folder_name in SKIP_FOLDERS:
        return True
    # Skip folders starting with ! (flexible auto-skip)
    if folder_name.startswith('!'):
        return True
    return False

class TVThumbnailGenerator:
    def __init__(self, api_key, target_dir, dry_run=False, verbose=False, image_width=300):
        self.api_key = api_key  # Not used for TVMaze
        self.target_dir = target_dir
        self.dry_run = dry_run
        self.verbose = verbose
        self.image_width = image_width
        self.tvmaze_base_url = "https://api.tvmaze.com"

        # Rate limiting: TMDB free tier allows ~50 requests per day
        self.request_delay = 0.5  # 500ms between requests

    def clean_show_name(self, folder_name):
        """Clean folder name to extract meaningful TV show title."""
        # Remove common patterns but keep structure
        patterns_to_remove = [
            r'\s*\(?\d{4}\)?(?:\s*\(?\d{4}\)?)*\s*$',  # Years at end like (2013) or 2013
            r'season\s*\d+(?:-\d+)?(?:\s*s\d+(?:-\d+)?)*',  # Season info
            r'\s*s\d+(?:-\d+)?(?:\s*-\s*\d+)?',  # S01-S08 patterns
            r'\s*\d{3,4}p\s*',  # Resolution like 1080p, 720p
            r'\s*web(?:-dl|\.dl)?\s*',  # WEB-DL, WEB
            r'\s*x\d{3}\s*',  # x265, x264, etc.
            r'\s*hevc\s*', r'\s*aac\s*', r'\s*eac3\s*', r'\s*dd\d+\.?\d*\s*',  # Audio codecs
            r'\s*amzn\s*', r'\s*netflix\s*', r'\s*hbo\s*', r'\s*disney\+?\s*',  # Streaming services
            r'\s*bluray\s*', r'\s*blu-ray\s*', r'\s*webrip\s*', r'\s*hdrip\s*', r'\s*dvdrip\s*',
            r'\s*\[.*?\]\s*',  # Anything in brackets like [UTR], [BRSHNKV]
            r'\s*-*$',  # Trailing dashes
            r'\s*-\s*\d+$',  # Trailing -YYYY
            r'.*$',  # Everything after certain patterns (be careful with this)
        ]

        name = folder_name.strip()
        name = urllib.parse.unquote(name)  # Decode URL-encoded names

        # Split on common separators and take the main title part
        separators = [' season', ' s01', ' (', ' [', ' - ', ' 1080p', ' 720p', ' x265', ' x264']
        main_title = name

        for sep in separators:
            if sep.lower() in name.lower():
                main_title = name.split(sep.lower())[0].strip()
                break

        # Remove specific patterns that indicate non-title content
        main_title = re.sub(r'\s+(complete|series|collection|episodes?|seasons?)\s*$', '', main_title, flags=re.IGNORECASE)

        # Handle specific known shows first
        lower_title = main_title.lower().strip()

        if 'agatha christie' in lower_title:
            if 'marple' in lower_title:
                return "Agatha Christie's Marple"
            elif 'poirot' in lower_title:
                return "Agatha Christie's Poirot"
            else:
                return main_title.strip()

        if 'brooklyn nine-nine' in lower_title or 'brooklyn nine nine' in lower_title:
            return 'Brooklyn Nine-Nine'

        if 'midsomer murders' in lower_title:
            return 'Midsomer Murders'

        if 'byomkesh bakshi' in lower_title:
            return 'Byomkesh Bakshi'

        if 'death in paradise' in lower_title:
            return 'Death in Paradise'

        # Generic title casing
        if lower_title == 'castle':
            return 'Castle'
        if lower_title == 'sherlock':
            return 'Sherlock'
        if lower_title == 'suits':
            return 'Suits'

        # For complex cases, try to reconstruct proper title
        words = re.findall(r'\b\w+\b', main_title)
        if words:
            # Capitalize each word, handling apostrophes
            capitalized_words = []
            for word in words:
                if "'" in word:
                    # Handle apostrophes: e.g., fisher's -> Fisher's
                    parts = word.split("'")
                    capitalized_word = parts[0][0].upper() + parts[0][1:].lower() + "'" + parts[1][0].upper() + parts[1][1:].lower()
                    capitalized_words.append(capitalized_word)
                elif len(word) <= 1:
                    capitalized_words.append(word.upper())
                else:
                    capitalized_words.append(word[0].upper() + word[1:].lower())

            result = ' '.join(capitalized_words)

            # Clean up some common formatting issues
            result = re.sub(r'\s+', ' ', result).strip()
            return result

        return main_title.strip()

    def search_tvmaze_show(self, show_name):
        """Search TVMaze for a TV show and return the best match."""
        if self.dry_run:
            # For dry run, return mock data to test name cleaning
            return {
                'name': show_name,
                'image': {'medium': 'https://via.placeholder.com/210x295?text=Poster'},
                'premiered': '2020',
                'rating': {'average': 8.0}
            }, None

        search_url = f"{self.tvmaze_base_url}/search/shows"
        params = {
            'q': show_name
        }

        try:
            time.sleep(self.request_delay)  # Rate limiting
            response = requests.get(search_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data:
                return None, f"No results found for '{show_name}'"

            # Get the best match - prefer exact name matches, then highest rating
            results = data

            if not results:
                return None, f"Empty results for '{show_name}'"

            # Sort by: exact name match first, then rating
            def sort_key(result):
                show = result.get('show', {})
                name_match = show.get('name', '').lower() == show_name.lower()
                rating = show.get('rating', {}).get('average', 0) or 0
                return (name_match, rating)

            try:
                results.sort(key=sort_key, reverse=True)
                best_match = results[0]['show']
                return best_match, None
            except (KeyError, IndexError) as e:
                return None, f"Failed to parse search results: {str(e)}"

        except requests.exceptions.RequestException as e:
            return None, f"API request failed: {str(e)}"

    def download_and_resize_poster(self, poster_path, output_path):
        """Download poster image and resize to target width."""
        if not poster_path:
            return False, "No poster path provided"

        # TVMaze provides full URLs, not relative paths
        image_url = poster_path

        try:
            time.sleep(self.request_delay)
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()

            # Open image with PIL
            img = Image.open(BytesIO(response.content))

            # Convert to RGB if necessary (handles PNG with transparency)
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')

            # Calculate height maintaining aspect ratio
            aspect_ratio = img.height / img.width
            new_height = int(self.image_width * aspect_ratio)

            # Resize
            resized_img = img.resize((self.image_width, new_height), Image.Resampling.LANCZOS)

            # Save as JPEG
            resized_img.save(output_path, 'JPEG', quality=95)
            return True, f"Saved {self.image_width}x{new_height} image"

        except Exception as e:
            return False, f"Image processing failed: {str(e)}"

    def process_show_folder(self, folder_path, folder_name):
        """Process a single show folder."""
        # Skip folders based on user's defined rules
        if should_skip_folder(folder_name):
            if self.verbose:
                print(f"  SKIPPED: '{folder_name}' (matches blacklist)")
            else:
                print(f"  Skipped (blacklist): {folder_name[:40]}{'...' if len(folder_name) > 40 else ''}")
            return "skipped_blacklist"

        show_name = self.clean_show_name(folder_name)

        if self.verbose:
            print(f"  Processing: '{folder_name}' → '{show_name}'")
        else:
            print(f"  Processing: {folder_name[:50]}{'...' if len(folder_name) > 50 else ''}")

        if self.dry_run:
            print(f"    (DRY RUN) Would search for: '{show_name}'")
            return "dry-run"

        # Check if index.jpg already exists
        index_path = os.path.join(folder_path, 'index.jpg')
        if os.path.exists(index_path):
            if self.verbose:
                print(f"    Skipped: index.jpg already exists")
            return "exists"

        # Search TVMaze
        show_data, error = self.search_tvmaze_show(show_name)
        if error:
            print(f"    ERROR: {error}")
            return "search_failed"

        if show_data is None:
            print(f"    ERROR: No results found for '{show_name}'")
            return "search_failed"

        try:
            poster_path = show_data.get('image', {}).get('medium')
        except AttributeError:
            print(f"    ERROR: Invalid data structure for {show_name}")
            return "search_failed"

        if not poster_path:
            print(f"    ERROR: No poster available for {show_data.get('name', show_name)}")
            return "no_poster"

        if self.verbose:
            print(f"    Found: {show_data.get('name')} ({show_data.get('premiered', 'Unknown year')[:4]})")

        # Download and resize
        success, msg = self.download_and_resize_poster(poster_path, index_path)
        if success:
            print(f"    SUCCESS: {msg}")
            return "success"
        else:
            print(f"    ERROR: {msg}")
            return "download_failed"

    def run(self):
        """Main processing function."""
        print("TV Series Thumbnail Generator")
        print(f"Target directory: {self.target_dir}")
        print(f"Image width: {self.image_width}px")
        print(f"Dry run: {'YES' if self.dry_run else 'NO'}")
        print("-" * 50)

        if not os.path.exists(self.target_dir):
            print(f"ERROR: Target directory '{self.target_dir}' not found")
            sys.exit(1)

        # Get all subdirectories
        folders = []
        try:
            for item in os.listdir(self.target_dir):
                item_path = os.path.join(self.target_dir, item)
                if os.path.isdir(item_path):
                    folders.append((item_path, item))
        except PermissionError as e:
            print(f"ERROR: Permission denied reading directory: {e}")
            sys.exit(1)

        if not folders:
            print("No folders found in target directory")
            sys.exit(0)

        print(f"Found {len(folders)} folders to process")
        print()

        # Process each folder
        stats = {
            'success': 0,
            'exists': 0,
            'skipped_blacklist': 0,
            'search_failed': 0,
            'no_poster': 0,
            'download_failed': 0,
            'dry-run': 0
        }

        for folder_path, folder_name in folders:
            result = self.process_show_folder(folder_path, folder_name)
            stats[result] += 1

        print("\n" + "=" * 50)
        print("SUMMARY:")
        print(f"  Total folders: {len(folders)}")
        print(f"  Success: {stats['success']}")
        print(f"  Skipped (already exists): {stats['exists']}")
        print(f"  Search failed: {stats['search_failed']}")
        print(f"  No poster available: {stats['no_poster']}")
        print(f"  Download failed: {stats['download_failed']}")
        if self.dry_run:
            print(f"  Dry run tests: {stats['dry-run']}")


def main():
    parser = argparse.ArgumentParser(description="Generate TV series thumbnails using TVMaze API (no key required)")
    parser.add_argument('--api-key', help='Not required for TVMaze (kept for compatibility)')
    parser.add_argument('--target-dir', required=True, help='Directory containing TV series folders')
    parser.add_argument('--image-width', type=int, default=300, help='Thumbnail width in pixels (default: 300)')
    parser.add_argument('--dry-run', action='store_true', help='Test mode - don\'t actually download images')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    generator = TVThumbnailGenerator(
        api_key=args.api_key,
        target_dir=args.target_dir,
        dry_run=args.dry_run,
        verbose=args.verbose,
        image_width=args.image_width
    )

    generator.run()


if __name__ == "__main__":
    main()
