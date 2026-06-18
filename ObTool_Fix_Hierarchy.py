import bpy
from mathutils import Matrix

def fix_outbreak_final_v3():
    nodes_info = {}
    meshes = []

    # 1. SALVATAGGIO DATI (Matrix World)
    for obj in bpy.data.objects:
        if "Node" in obj.name:
            name = obj.name.split(".")[0]
            # Salviamo la posizione assoluta per non sbagliare le proporzioni
            nodes_info[name] = {
                'matrix': obj.matrix_world.copy(),
                'parent': obj.parent.name.split(".")[0] if (obj.parent and "Node" in obj.parent.name) else None
            }
            if obj.type == 'ARMATURE':
                for bone in obj.data.bones:
                    b_name = bone.name.split(".")[0]
                    nodes_info[b_name] = {
                        'matrix': (obj.matrix_world @ bone.matrix_local).copy(),
                        'parent': bone.parent.name.split(".")[0] if bone.parent else name
                    }
        elif obj.type == 'MESH':
            meshes.append(obj)

    # 2. PULIZIA
    for mesh in meshes:
        mesh.parent = None
        mesh.matrix_world = mesh.matrix_world.copy()
    
    for o in [obj for obj in bpy.data.objects if "Node" in obj.name]:
        bpy.data.objects.remove(o, do_unlink=True)
    for a in [arm for arm in bpy.data.armatures if "Node" in arm.name]:
        bpy.data.armatures.remove(a)

    # 3. CREAZIONE ARMATURA
    arm_data = bpy.data.armatures.new("Node0_Data")
    arm_data.display_type = 'STICK' # Rende le ossa più visibili nell'animazione
    node0_obj = bpy.data.objects.new("Node0", arm_data)
    bpy.context.collection.objects.link(node0_obj)

    bpy.context.view_layer.objects.active = node0_obj
    bpy.ops.object.mode_set(mode='EDIT')
    
    # 4. CREAZIONE OSSA CON "TAIL" VISIBILE
    for name, info in nodes_info.items():
        if name == "Node0": continue
        bone = arm_data.edit_bones.new(name)
        # Impostiamo la matrice
        bone.matrix = info['matrix']
        # Importante: diamo una lunghezza all'osso altrimenti scompare
        bone.length = 0.05 

    # 5. GERARCHIA FERREA (Node2 come Hub)
    eb = arm_data.edit_bones
    for name, info in nodes_info.items():
        if name in ["Node0", "Node1"]: continue
        bone = eb.get(name)
        if not bone: continue
        
        # Se è Node2, va sotto Node1
        if name == "Node2":
            bone.parent = eb.get("Node1")
        # Se è Node3 o Node10 (o altri), vanno sotto Node2 o il loro parent
        else:
            p_name = info['parent']
            if p_name == "Node2" or p_name == "Node0" or p_name == "Node1":
                bone.parent = eb.get("Node2")
            elif p_name and eb.get(p_name):
                bone.parent = eb.get(p_name)

    bpy.ops.object.mode_set(mode='OBJECT')

    # 6. FIX MESH E SCALE
    for mesh in meshes:
        mesh.parent = node0_obj
        # Applichiamo la scala per evitare distorsioni (torso lungo)
        mesh.matrix_world = mesh.matrix_world
        mod = mesh.modifiers.new(name="Armature", type='ARMATURE')
        mod.object = node0_obj

    # 7. RENDI OSSA VISIBILI SOPRA LA MESH
    node0_obj.show_in_front = True

fix_outbreak_final_v3()