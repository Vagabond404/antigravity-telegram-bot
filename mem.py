#!/usr/bin/env python3
import sys
import argparse
import json
from memory_manager import (
    add_or_update_memory, search_memories, list_memories,
    delete_memory, get_memory_graph, get_summary_html
)

def main():
    parser = argparse.ArgumentParser(description='Antigravity Second Brain & Memory CLI')
    subparsers = parser.add_subparsers(dest='command')

    # add
    p_add = subparsers.add_parser('add', help='Add or update a memory')
    p_add.add_argument('content', help='Fact / instruction / memory text')
    p_add.add_argument('--category', '-c', default='general', help='Category (user_profile, project, infra, etc.)')
    p_add.add_argument('--key', '-k', default=None, help='Short unique key/topic')
    p_add.add_argument('--tags', '-t', default='', help='Comma-separated tags')
    p_add.add_argument('--related', '-r', default='', help='Comma-separated memory IDs or keys connected')
    p_add.add_argument('--importance', '-i', type=int, default=3, help='Importance 1-5')

    # search
    p_search = subparsers.add_parser('search', help='Search memories by keywords/semantics')
    p_search.add_argument('query', help='Search terms')
    p_search.add_argument('--category', '-c', default=None, help='Filter by category')
    p_search.add_argument('--limit', '-l', type=int, default=5)

    # list
    p_list = subparsers.add_parser('list', help='List recent memories')
    p_list.add_argument('--category', '-c', default=None)
    p_list.add_argument('--limit', '-l', type=int, default=20)

    # delete
    p_del = subparsers.add_parser('delete', help='Delete a memory by ID')
    p_del.add_argument('id', type=int)

    # graph
    p_graph = subparsers.add_parser('graph', help='Export memory connection graph as JSON')

    args = parser.parse_args()

    if args.command == 'add':
        mid = add_or_update_memory(
            content=args.content,
            category=args.category,
            key=args.key,
            tags=args.tags,
            related_to=args.related,
            importance=args.importance
        )
        print(f"✅ Souvenir mémorisé avec succès [ID: #{mid}, Catégorie: {args.category}]")

    elif args.command == 'search':
        res = search_memories(args.query, limit=args.limit, category=args.category)
        if not res:
            print("🔍 Aucun souvenir correspondant trouvé.")
        else:
            print(f"🧠 {len(res)} souvenir(s) trouvé(s) :")
            for m in res:
                key_s = f" ({m['key']})" if m.get('key') else ""
                print(f"  • [#{m['id']}] [{m['category']}{key_s}] : {m['content']}")

    elif args.command == 'list':
        res = list_memories(category=args.category, limit=args.limit)
        print(f"📋 {len(res)} souvenir(s) dans la mémoire :")
        for m in res:
            key_s = f" ({m['key']})" if m.get('key') else ""
            print(f"  • [#{m['id']}] [{m['category']}{key_s}] : {m['content']}")

    elif args.command == 'delete':
        ok = delete_memory(args.id)
        print(f"🗑️ Souvenir #{args.id} supprimé." if ok else f"❌ Souvenir #{args.id} introuvable.")

    elif args.command == 'graph':
        g = get_memory_graph()
        print(json.dumps(g, indent=2))

    else:
        parser.print_help()

if __name__ == '__main__':
    main()