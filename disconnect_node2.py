"""
Disconnect Node2 from its parent bone (Node1) to unlock Location in Pose Mode.
Esegui in Blender Text Editor con l'armatura HD selezionata/attiva.

Questo NON sposta visivamente nulla nel rest pose: cambia solo use_connect.
"""
import bpy

def disconnect_node2():
    arm = bpy.data.objects.get("Node2") or bpy.data.objects.get("Node0")
    
    if not arm or arm.type != 'ARMATURE':
        print("ERROR: No armature found (Node2 or Node0)")
        return
    
    print(f"Armature: {arm.name}")
    
    if "Node1" not in arm.pose.bones or "Node2" not in arm.pose.bones:
        print("This is not an HD model (Node1/Node2 are not bones). Nothing to do.")
        return
    
    current_mode = arm.mode
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    
    eb2 = arm.data.edit_bones.get("Node2")
    
    if not eb2:
        print("ERROR: Node2 bone not found in edit_bones")
        bpy.ops.object.mode_set(mode=current_mode)
        return
    
    print(f"\nNode2 BEFORE:")
    print(f"  use_connect: {eb2.use_connect}")
    print(f"  head: ({eb2.head.x:.4f}, {eb2.head.y:.4f}, {eb2.head.z:.4f})")
    print(f"  parent: {eb2.parent.name if eb2.parent else 'None'}")
    
    if eb2.use_connect:
        eb2.use_connect = False
        print(f"\n✅ Disconnected Node2 from parent")
    else:
        print(f"\nNode2 was already disconnected (use_connect=False)")
    
    print(f"\nNode2 AFTER:")
    print(f"  use_connect: {eb2.use_connect}")
    print(f"  head: ({eb2.head.x:.4f}, {eb2.head.y:.4f}, {eb2.head.z:.4f})")
    
    bpy.ops.object.mode_set(mode=current_mode)
    
    print(f"\n{'='*50}")
    print("DONE. Check Pose Mode -> Node2 -> Location should be editable now.")
    print(f"{'='*50}")

if __name__ == "__main__":
    disconnect_node2()