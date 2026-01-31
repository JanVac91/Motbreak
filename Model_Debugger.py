import bpy
import math

def super_debug_outbreak():
    print("\n" + "="*90)
    print("SUPER DEBUG REPORT: GERARCHIA EMPTY -> ARMATURA -> OSSA")
    print("="*90)

    # 1. ANALISI ROOT (EMPTY NODE0)
    root_obj = bpy.data.objects.get("Node0")
    
    if root_obj:
        print(f"[LIVELLO 0: ROOT]")
        print(f"Nome: {root_obj.name} | Tipo: {root_obj.type} | Scala: {root_obj.scale}")
        print(f"Rotazione: {root_obj.rotation_euler} | Parent: {root_obj.parent.name if root_obj.parent else 'NESSUNO'}")
        
        # Cerca l'armatura dentro l'Empty o se Node0 stesso è l'armatura
        armatures = [child for child in root_obj.children if child.type == 'ARMATURE']
        if root_obj.type == 'ARMATURE': armatures.append(root_obj)
        
        if not armatures:
            print("!!! ATTENZIONE: Nessuna Armatura trovata sotto Node0")
        else:
            for arm in armatures:
                analyze_armature_deep(arm)
    else:
        print("!!! ERRORE: Oggetto 'Node0' non trovato. Seleziona l'oggetto principale.")

def analyze_armature_deep(arm_obj):
    print(f"\n[LIVELLO 1: ARMATURA]")
    print(f"Nome Oggetto: {arm_obj.name} | Data Block: {arm_obj.data.name}")
    print(f"Scala: {arm_obj.scale} | Rotazione: {arm_obj.rotation_euler}")
    
    print(f"\n{'Nome Osso':<15} | {'Parent':<15} | {'Length':<8} | {'Scale Locale':<20}")
    print("-" * 80)
    
    # Analizziamo le ossa (Pose Bones per le trasformazioni attive)
    for p_bone in arm_obj.pose.bones:
        bone_data = arm_obj.data.bones[p_bone.name]
        p_name = bone_data.parent.name if bone_data.parent else "ROOT"
        
        # Debug scala (se non è 1.0, deforma il torso)
        s = p_bone.scale
        scale_str = f"({s.x:.3f}, {s.y:.3f}, {s.z:.3f})"
        warn = " <!! WARN: SCALE" if (abs(1.0 - s.x) > 0.01 or abs(1.0 - s.y) > 0.01) else ""
        
        print(f"{p_bone.name:<15} | {p_name:<15} | {bone_data.length:<8.4f} | {scale_str:<20}{warn}")

    # 2. VERIFICA COLLEGAMENTI CRITICI
    print(f"\n[LIVELLO 2: VERIFICA GERARCHIA CRITICA]")
    critical_nodes = ["Node1", "Node2", "Node3", "Node10"]
    for name in critical_nodes:
        bone = arm_obj.data.bones.get(name)
        if bone:
            p = bone.parent.name if bone.parent else "NESSUNO"
            print(f"- {name}: Parent -> {p} {'[OK]' if (name == 'Node3' or name == 'Node10') and p == 'Node2' else ''}")
        else:
            print(f"- {name}: !!! MANCANTE")

    # 3. ANALISI MESH
    print(f"\n[LIVELLO 3: MESH E PESI]")
    for child in bpy.data.objects:
        if child.type == 'MESH' and (child.parent == arm_obj or child.parent == root_obj):
            arm_mod = next((m for m in child.modifiers if m.type == 'ARMATURE'), None)
            print(f"- Mesh: {child.name} | Scale: {child.scale}")
            print(f"  Parent: {child.parent.name} | Modificatore Armature: {'OK' if arm_mod else 'MANCANTE'}")

    print("\n" + "="*90)
    print("Fine Debug. Controlla la System Console (Window -> Toggle System Console)")

# Esecuzione
super_debug_outbreak()