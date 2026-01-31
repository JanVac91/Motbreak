import bpy

# --- 1. CLEANING LOGIC ---
def execute_animation_cleaning(mode):
    obj = bpy.context.active_object
    if not obj or not obj.animation_data or not obj.animation_data.action:
        return False
    
    act = obj.animation_data.action
    f_s, f_e = int(act.frame_range[0]), int(act.frame_range[1])
    duration = f_e - f_s
    
    # Define frame step based on preset
    if mode == 'MAX': step = 2
    elif mode == 'MEDIUM': step = 5
    elif mode == 'LOW': step = 10
    else: step = max(1, int(duration / 4)) # Ultra Low (Quarters)
    
    # Frames to keep
    to_keep = {f_s, f_e}
    i = f_s
    while i < f_e:
        to_keep.add(i)
        i += step
        
    for fc in act.fcurves:
        # Get keyframe points reference
        kf_points = fc.keyframe_points
        # Iterate backwards to avoid index mismatch during removal
        for j in reversed(range(len(kf_points))):
            kp = kf_points[j]
            if int(kp.co[0]) not in to_keep:
                kf_points.remove(kp)
        
        fc.update()
    return True

# --- 2. OPERATOR (POP-UP DIALOG) ---
class POSE_OT_AnimKeyframeCleaner(bpy.types.Operator):
    bl_idname = "pose.animation_keyframe_cleaner"
    bl_label = "Animation Keyframe Cleaner"
    bl_options = {'REGISTER', 'UNDO'}

    preset: bpy.props.EnumProperty(
        name="Accuracy Mode",
        items=[('MAX', "Max (Step 2)", "High fidelity"),
               ('MEDIUM', "Medium (Step 5)", "Balanced"),
               ('LOW', "Low (Step 10)", "Aggressive optimization"),
               ('ULTRA', "Ultra Low (Quarters)", "Only 4 main keyframes")]
    )

    def execute(self, context):
        try:
            if execute_animation_cleaning(self.preset):
                self.report({'INFO'}, f"Animation Keyframe Cleaner: {self.preset} mode applied")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Cleaner Error: {str(e)}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

# --- 3. CONTEXT MENU INTEGRATION ---
def draw_pose_menu(self, context):
    self.layout.separator()
    self.layout.operator("pose.animation_keyframe_cleaner", text="Animation Keyframe Cleaner", icon='ANIM')

# --- 4. REGISTRATION ---
def register():
    bpy.utils.register_class(POSE_OT_AnimKeyframeCleaner)
    # Add to Pose Mode right-click menu
    bpy.types.VIEW3D_MT_pose_context_menu.append(draw_pose_menu)

def unregister():
    bpy.utils.unregister_class(POSE_OT_AnimKeyframeCleaner)
    bpy.types.VIEW3D_MT_pose_context_menu.remove(draw_pose_menu)

if __name__ == "__main__":
    try: unregister()
    except: pass
    register()