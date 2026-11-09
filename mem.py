#!/usr/bin/env python3
"""
mem.py - Second Brain, Person Profiles, Social Graph & Long-Term Memory CLI
Enhanced for Antigravity Telegram Agent v5.1
"""
import sys
import os
import argparse
import json

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from memory_manager import (
    add_or_update_memory, search_memories, list_memories,
    delete_memory, get_memory_graph, get_summary_html,
    save_person, add_person_fact, get_person, list_persons,
    delete_person, add_relationship, list_relationships, delete_relationship
)

def main():
    parser = argparse.ArgumentParser(description='Antigravity Second Brain & Advanced Long-Term Memory CLI')
    parser.add_argument('--user-id', '-u', default=os.environ.get("AGY_USER_ID", "default"), help='User ID for isolated memory partition')
    parser.add_argument('--shared', action='store_true', help='Store memory in shared/global space across all users')
    subparsers = parser.add_subparsers(dest='command')

    # add memory
    p_add = subparsers.add_parser('add', help='Add or update a memory')
    p_add.add_argument('content', help='Fact / instruction / memory text')
    p_add.add_argument('--category', '-c', default='general', help='Category (profile, preferences, projet, infra, rules, general)')
    p_add.add_argument('--key', '-k', default=None, help='Short unique key/topic')
    p_add.add_argument('--tags', '-t', default='', help='Comma-separated tags')
    p_add.add_argument('--related', '-r', default='', help='Comma-separated memory IDs or keys connected')
    p_add.add_argument('--importance', '-i', type=int, default=3, help='Importance 1-5')
    p_add.add_argument('--shared', action='store_true', help='Store as shared/global memory across all users')

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
    p_graph = subparsers.add_parser('graph', help='Export memory & social connection graph as JSON')

    # person subcommands
    p_person = subparsers.add_parser('person', help='Manage individual people profiles, tone preferences & facts')
    person_sub = p_person.add_subparsers(dest='person_action')

    # person add/set
    p_padd = person_sub.add_parser('add', help='Add or update a person profile')
    p_padd.add_argument('name', help='Full name or identifier of the person')
    p_padd.add_argument('--role', default='', help='Role or occupation (e.g. "Admin principal", "Client", "Designer")')
    p_padd.add_argument('--relation', default='', help='Relationship with user (e.g. "Utilisateur principal", "Collègue", "Ami")')
    p_padd.add_argument('--tone', default='', help='Tone / speech instruction (e.g. "Tutoiement direct et concis", "Vouvoiement formel et très courtois")')
    p_padd.add_argument('--notes', default='', help='Freeform background notes')
    p_padd.add_argument('--aliases', default='', help='Comma-separated nicknames / aliases')
    p_padd.add_argument('--shared', action='store_true', help='Store person profile as shared across all users')

    # person fact
    p_pfact = person_sub.add_parser('fact', help='Record a fact about a person')
    p_pfact.add_argument('name', help='Name of the person')
    p_pfact.add_argument('fact', help='Fact content')
    p_pfact.add_argument('--shared', action='store_true', help='Store fact in shared person profile')

    # person get
    p_pget = person_sub.add_parser('get', help='Get full details for a person')
    p_pget.add_argument('name', help='Name of the person')

    # person list
    person_sub.add_parser('list', help='List all registered person profiles')

    # person delete
    p_pdel = person_sub.add_parser('delete', help='Delete a person profile')
    p_pdel.add_argument('name', help='Name of the person')

    # relate subcommands (Social connections)
    p_rel = subparsers.add_parser('relate', help='Manage social graph & connections between people')
    rel_sub = p_rel.add_subparsers(dest='rel_action')

    # relate add
    p_radd = rel_sub.add_parser('add', help='Add a relationship between person A and person B')
    p_radd.add_argument('person_a', help='First person name')
    p_radd.add_argument('relation_type', help='Relationship type (e.g. colleague, friend, lead, client, brother)')
    p_radd.add_argument('person_b', help='Second person name')
    p_radd.add_argument('--details', default='', help='Additional details about the relation')
    p_radd.add_argument('--shared', action='store_true', help='Store relationship as shared across all users')

    # relate list
    p_rlist = rel_sub.add_parser('list', help='List all relationships')
    p_rlist.add_argument('--person', default=None, help='Filter by person name')

    # relate delete
    p_rdel = rel_sub.add_parser('delete', help='Delete a relationship by ID')
    p_rdel.add_argument('id', type=int, help='Relationship ID')

    args = parser.parse_args()
    uid = getattr(args, 'user_id', os.environ.get("AGY_USER_ID", "default"))
    is_shared = getattr(args, 'shared', False)
    target_uid = "global" if is_shared else uid

    if args.command == 'add':
        mid = add_or_update_memory(
            content=args.content,
            category=args.category,
            key=args.key,
            tags=args.tags,
            related_to=args.related,
            importance=args.importance,
            user_id=target_uid,
        )
        scope_str = "Shared (global)" if is_shared else f"Personal ({uid})"
        print(f"✅ Memory stored successfully [ID: #{mid}, Category: {args.category}, Scope: {scope_str}]")

    elif args.command == 'search':
        res = search_memories(args.query, limit=args.limit, category=args.category, user_id=uid, include_shared=True)
        if not res:
            print("🔍 No matching memory found.")
        else:
            print(f"🧠 Found {len(res)} memory entry/entries (Personal [{uid}] + Shared):")
            for m in res:
                key_s = f" ({m['key']})" if m.get('key') else ""
                m_uid = m.get('user_id', '')
                scope_tag = "🌐 [Shared]" if m_uid in ('global', 'shared', 'default') else "👤 [Personal]"
                print(f"  • [#{m['id']}] {scope_tag} [{m['category']}{key_s}] : {m['content']}")

    elif args.command == 'list':
        res = list_memories(category=args.category, limit=args.limit, user_id=uid, include_shared=True)
        print(f"📋 {len(res)} memory entry/entries (Personal [{uid}] + Shared):")
        for m in res:
            key_s = f" ({m['key']})" if m.get('key') else ""
            m_uid = m.get('user_id', '')
            scope_tag = "🌐 [Shared]" if m_uid in ('global', 'shared', 'default') else "👤 [Personal]"
            print(f"  • [#{m['id']}] {scope_tag} [{m['category']}{key_s}] : {m['content']}")

    elif args.command == 'delete':
        ok = delete_memory(args.id, user_id=uid)
        print(f"🗑️ Memory #{args.id} deleted." if ok else f"❌ Memory #{args.id} not found.")

    elif args.command == 'graph':
        g = get_memory_graph(user_id=uid, include_shared=True)
        print(json.dumps(g, indent=2, ensure_ascii=False))

    elif args.command == 'person':
        act = args.person_action
        if act == 'add':
            pid = save_person(
                name=args.name,
                role=args.role,
                relationship_to_user=args.relation,
                tone_preference=args.tone,
                notes=args.notes,
                aliases=args.aliases,
                user_id=target_uid,
            )
            scope_str = "Shared (global)" if is_shared else f"Personal ({uid})"
            print(f"👤 Person profile for '{args.name}' saved successfully [ID: #{pid}, Scope: {scope_str}].")
        elif act == 'fact':
            ok = add_person_fact(args.name, args.fact, user_id=target_uid)
            print(f"📝 Fact added to '{args.name}'." if ok else f"❌ Failed to add fact for '{args.name}'.")
        elif act == 'get':
            p = get_person(args.name, user_id=uid, include_shared=True)
            if p:
                p_uid = p.get('user_id', '')
                scope_str = "🌐 Shared" if p_uid in ('global', 'shared', 'default') else f"👤 Personal ({p_uid})"
                print(f"👤 Profile of {p['name']} [ID #{p['id']}, Scope: {scope_str}]:")
                if p['role']:
                    print(f"  • Role : {p['role']}")
                if p['relationship_to_user']:
                    print(f"  • Relation to user : {p['relationship_to_user']}")
                if p['tone_preference']:
                    print(f"  • Speech tone directive : {p['tone_preference']}")
                if p['aliases']:
                    print(f"  • Aliases : {p['aliases']}")
                if p['notes']:
                    print(f"  • Notes : {p['notes']}")
                if p['facts']:
                    print(f"  • Known facts ({len(p['facts'])}) :")
                    for f in p['facts']:
                        print(f"      - {f}")
            else:
                print(f"❌ Person '{args.name}' not found.")
        elif act == 'list':
            persons = list_persons(user_id=uid, include_shared=True)
            print(f"👥 {len(persons)} person profile(s) (Personal [{uid}] + Shared):")
            for p in persons:
                tone = f" | Tone: {p['tone_preference']}" if p.get('tone_preference') else ""
                rel = f" | Relation: {p['relationship_to_user']}" if p.get('relationship_to_user') else ""
                p_uid = p.get('user_id', '')
                scope_tag = "🌐 [Shared]" if p_uid in ('global', 'shared', 'default') else "👤 [Personal]"
                print(f"  • [#{p['id']}] {scope_tag} {p['name']}{rel}{tone}")
        elif act == 'delete':
            ok = delete_person(args.name, user_id=uid)
            print(f"🗑️ Profile '{args.name}' deleted." if ok else f"❌ Profile '{args.name}' not found.")
        else:
            p_person.print_help()

    elif args.command == 'relate':
        act = args.rel_action
        if act == 'add':
            rid = add_relationship(
                person_a=args.person_a,
                relation_type=args.relation_type,
                person_b=args.person_b,
                details=args.details,
                user_id=target_uid,
            )
            scope_str = "Shared (global)" if is_shared else f"Personal ({uid})"
            print(f"🔗 Relationship saved [ID #{rid}, Scope: {scope_str}] : {args.person_a} ➔ {args.relation_type} ➔ {args.person_b}")
        elif act == 'list':
            rels = list_relationships(person=args.person, user_id=uid, include_shared=True)
            print(f"🤝 {len(rels)} relationship(s) (Personal [{uid}] + Shared):")
            for r in rels:
                det = f" ({r['details']})" if r.get('details') else ""
                r_uid = r.get('user_id', '')
                scope_tag = "🌐 [Shared]" if r_uid in ('global', 'shared', 'default') else "👤 [Personal]"
                print(f"  • [#{r['id']}] {scope_tag} {r['person_a']} ➔ {r['relation_type']} ➔ {r['person_b']}{det}")
        elif act == 'delete':
            ok = delete_relationship(args.id, user_id=uid)
            print(f"🗑️ Relationship #{args.id} deleted." if ok else f"❌ Relationship #{args.id} not found.")
        else:
            p_rel.print_help()

    else:
        parser.print_help()

if __name__ == '__main__':
    main()
