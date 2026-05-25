#!/usr/bin/env python3
"""
Weekly X Bookmark Digest Generator

Reads the latest bookmark analysis and generates a formatted digest
that can be sent via email, Telegram, or saved to a file.
"""
import json
import glob
import os
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("/app/output")
DIGEST_DIR = Path("/app/output/digests")

def get_latest_summary():
    """Get the most recent bookmark summary file."""
    files = glob.glob(str(OUTPUT_DIR / "bookmark_summary_*.json"))
    if not files:
        return None
    return max(files, key=os.path.getctime)

def generate_digest():
    """Generate a formatted digest from the latest analysis."""
    summary_file = get_latest_summary()
    if not summary_file:
        return "No bookmark analysis found."
    
    with open(summary_file) as f:
        data = json.load(f)
    
    lines = []
    lines.append("=" * 60)
    lines.append("X BOOKMARK WEEKLY DIGEST")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 60)
    lines.append("")
    
    # Summary stats
    total = data.get('total_processed', 0)
    lines.append(f"Bookmarks Processed: {total}")
    lines.append("")
    
    # By folder
    folders = data.get('by_folder', {})
    if folders:
        lines.append("Categories:")
        for folder, count in folders.items():
            lines.append(f"  • {folder}: {count}")
        lines.append("")

    edge_counts = data.get('edge_case_counts', {})
    if edge_counts:
        lines.append("Edge cases:")
        for key, count in edge_counts.items():
            lines.append(f"  • {key}: {count}")
        lines.append("")
    
    # Insights
    insights = data.get('insights', [])
    if insights:
        lines.append("KEY INSIGHTS")
        lines.append("-" * 40)
        for i, insight in enumerate(insights, 1):
            author = insight.get('author', 'Unknown')
            text = insight.get('insight', '')
            url = insight.get('url', '')
            lines.append(f"{i}. @{author}: {text}")
            if url:
                lines.append(f"   {url}")
            lines.append("")
    
    # Action items
    actions = data.get('action_items', [])
    if actions:
        lines.append("ACTION ITEMS")
        lines.append("-" * 40)
        for i, action in enumerate(actions, 1):
            author = action.get('author', 'Unknown')
            text = action.get('action', '')
            url = action.get('url', '')
            lines.append(f"{i}. @{author}: {text}")
            if url:
                lines.append(f"   {url}")
            lines.append("")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)

def save_digest():
    """Generate and save the digest."""
    DIGEST_DIR.mkdir(exist_ok=True)
    
    digest = generate_digest()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    digest_file = DIGEST_DIR / f"digest_{timestamp}.txt"
    
    with open(digest_file, 'w') as f:
        f.write(digest)
    
    print(f"Digest saved to: {digest_file}")
    print("\n" + digest)
    
    return str(digest_file)

if __name__ == "__main__":
    save_digest()
