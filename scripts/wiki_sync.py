#!/usr/bin/env python3
"""
Wiki Sync - X Bookmark Insights to Wiki

Reads the latest bookmark analysis and updates the wiki:
1. Creates/updates raw/articles/x-bookmark-digest.md
2. Updates concepts/x-bookmark-insights.md with new insights
3. Appends to wiki/log.md
"""
import json
import glob
import os
import re
from datetime import datetime
from pathlib import Path

WIKI_PATH = Path("/app/wiki")
OUTPUT_DIR = Path("/app/output")

def get_latest_summary():
    """Get the most recent bookmark summary file."""
    files = glob.glob(str(OUTPUT_DIR / "bookmark_summary_*.json"))
    if not files:
        return None
    return max(files, key=os.path.getctime)

def get_latest_analysis():
    """Get the most recent full analysis file."""
    files = glob.glob(str(OUTPUT_DIR / "bookmark_analysis_*.json"))
    if not files:
        return None
    return max(files, key=os.path.getctime)

def slugify(text):
    """Convert text to wiki slug."""
    return re.sub(r'[^\w\s-]', '', text).strip().lower().replace(' ', '-')

def update_wiki():
    """Sync bookmark insights to wiki."""
    summary_file = get_latest_summary()
    analysis_file = get_latest_analysis()
    
    if not summary_file:
        print("No bookmark analysis found.")
        return
    
    with open(summary_file) as f:
        summary = json.load(f)
    
    with open(analysis_file) as f:
        analysis = json.load(f)
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Create raw digest
    raw_dir = WIKI_PATH / "raw" / "articles"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    raw_file = raw_dir / f"x-bookmark-digest-{today}.md"
    with open(raw_file, 'w') as f:
        f.write("---\n")
        f.write(f"source_url: x.com/i/bookmarks\n")
        f.write(f"ingested: {today}\n")
        f.write(f"bookmarks_processed: {summary.get('total_processed', 0)}\n")
        f.write("---\n\n")
        f.write(f"# X Bookmark Digest - {today}\n\n")
        f.write(f"**Bookmarks processed:** {summary.get('total_processed', 0)}\n\n")
        
        # Categories
        folders = summary.get('by_folder', {})
        if folders:
            f.write("## Categories\n")
            for folder, count in folders.items():
                f.write(f"- {folder}: {count}\n")
            f.write("\n")

        edge_counts = summary.get('edge_case_counts', {})
        if edge_counts:
            f.write("## Edge Cases\n")
            for key, count in edge_counts.items():
                f.write(f"- {key}: {count}\n")
            f.write("\n")
        
        # Insights
        insights = summary.get('insights', [])
        if insights:
            f.write("## Insights\n\n")
            for i, insight in enumerate(insights, 1):
                author = insight.get('author', 'Unknown')
                text = insight.get('insight', '')
                url = insight.get('url', '')
                f.write(f"### {i}. @{author}\n\n")
                f.write(f"{text}\n\n")
                if url:
                    f.write(f"Source: {url}\n\n")
        
        # Action items
        actions = summary.get('action_items', [])
        if actions:
            f.write("## Action Items\n\n")
            for i, action in enumerate(actions, 1):
                author = action.get('author', 'Unknown')
                text = action.get('action', '')
                url = action.get('url', '')
                f.write(f"{i}. **@{author}**: {text}\n")
                if url:
                    f.write(f"   {url}\n")
            f.write("\n")
    
    print(f"Raw digest saved: {raw_file}")
    
    # 2. Update insights page
    insights_file = WIKI_PATH / "concepts" / "x-bookmark-insights.md"
    
    if insights_file.exists():
        with open(insights_file) as f:
            content = f.read()
        
        # Update the updated date
        content = re.sub(
            r'updated: \d{4}-\d{2}-\d{2}',
            f'updated: {today}',
            content
        )
        
        # Add new insights section
        new_section = f"\n## Insights from {today}\n\n"
        new_section += f"**Bookmarks processed:** {summary.get('total_processed', 0)}\n\n"
        
        for insight in insights:
            author = insight.get('author', 'Unknown')
            text = insight.get('insight', '')
            url = insight.get('url', '')
            new_section += f"### @{author}\n\n"
            new_section += f"{text}\n\n"
            if url:
                new_section += f"Source: {url}\n\n"
        
        for action in summary.get('action_items', []):
            author = action.get('author', 'Unknown')
            text = action.get('action', '')
            new_section += f"**Action:** @{author} - {text}\n\n"
        
        # Insert before "## Related" section
        related_idx = content.find("## Related")
        if related_idx >= 0:
            content = content[:related_idx] + new_section + "\n" + content[related_idx:]
        else:
            content += "\n" + new_section
        
        with open(insights_file, 'w') as f:
            f.write(content)
        
        print(f"Insights page updated: {insights_file}")
    else:
        print(f"Insights page not found: {insights_file}")
    
    # 3. Append to log
    log_file = WIKI_PATH / "log.md"
    with open(log_file, 'a') as f:
        f.write(f"\n## [{today}] ingest | X Bookmark Digest\n")
        f.write(f"- Bookmarks processed: {summary.get('total_processed', 0)}\n")
        f.write(f"- Insights extracted: {len(insights)}\n")
        f.write(f"- Action items: {len(summary.get('action_items', []))}\n")
        f.write(f"- Raw saved to: raw/articles/x-bookmark-digest-{today}.md\n")
        f.write(f"- Updated: concepts/x-bookmark-insights.md\n")
    
    print(f"Log updated: {log_file}")
    print("\nWiki sync complete!")

if __name__ == "__main__":
    update_wiki()
