bl_info = {
    "name": "Delete All Vertex Groups (Selected)",
    "author": "ChatGPT",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar (N) > Vertex",
    "description": "Delete all vertex groups from selected mesh objects",
    "category": "Object",
}

import bpy
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import BoolProperty, PointerProperty


def is_mesh_object(obj):
    return obj is not None and obj.type == "MESH"


def remove_weight_related_modifiers(obj):
    """
    Optional: Remove modifiers that are commonly tied to vertex groups.
    Adjust list as needed.
    """
    to_remove = []
    for m in obj.modifiers:
        if m.type in {"ARMATURE", "HOOK", "LATTICE", "MESH_DEFORM", "SURFACE_DEFORM", "CAST"}:
            to_remove.append(m.name)
    for name in to_remove:
        obj.modifiers.remove(obj.modifiers.get(name))
    return len(to_remove)


class VGDEL_Settings(PropertyGroup):
    remove_related_modifiers: BoolProperty(
        name="Remove related modifiers",
        description="Also remove common modifiers that may rely on vertex groups (Armature, Hook, etc.)",
        default=False,
    )


class OBJECT_OT_delete_all_vertex_groups_selected(Operator):
    bl_idname = "object.delete_all_vertex_groups_selected"
    bl_label = "Delete All Vertex Groups"
    bl_description = "Delete all vertex groups from selected mesh objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.vgdel_settings
        selected = context.selected_objects

        if not selected:
            self.report({"WARNING"}, "No objects selected.")
            return {"CANCELLED"}

        total_groups_deleted = 0
        total_objects_affected = 0
        total_mods_deleted = 0
        skipped = 0

        for obj in selected:
            if not is_mesh_object(obj):
                skipped += 1
                continue

            vg_count = len(obj.vertex_groups)
            if vg_count == 0:
                continue

            # Delete all vertex groups
            obj.vertex_groups.clear()

            total_groups_deleted += vg_count
            total_objects_affected += 1

            if settings.remove_related_modifiers:
                total_mods_deleted += remove_weight_related_modifiers(obj)

        msg = f"Deleted {total_groups_deleted} vertex groups from {total_objects_affected} objects."
        if settings.remove_related_modifiers:
            msg += f" Removed {total_mods_deleted} related modifiers."
        if skipped > 0:
            msg += f" Skipped {skipped} non-mesh objects."

        self.report({"INFO"}, msg)
        return {"FINISHED"}


class VIEW3D_PT_vg_delete_panel(Panel):
    bl_label = "Vertex Group Tools"
    bl_idname = "VIEW3D_PT_vg_delete_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vertex"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.vgdel_settings

        col = layout.column(align=True)
        col.prop(settings, "remove_related_modifiers")
        col.separator()
        col.operator(OBJECT_OT_delete_all_vertex_groups_selected.bl_idname, icon="X")


classes = (
    VGDEL_Settings,
    OBJECT_OT_delete_all_vertex_groups_selected,
    VIEW3D_PT_vg_delete_panel,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.vgdel_settings = PointerProperty(type=VGDEL_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "vgdel_settings"):
        del bpy.types.Scene.vgdel_settings
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
