bl_info = {
    "name": "Create Vertex Group From Clean Object Name + Fill Weights (Selected)",
    "author": "ChatGPT",
    "version": (1, 2, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar (N) > Vertex",
    "description": "Create a vertex group per selected mesh object from cleaned name, then fill all vertices with weight 1.0 (keeps .L/.R)",
    "category": "Object",
}

import bpy
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import BoolProperty, PointerProperty


def is_mesh_object(obj):
    return obj is not None and obj.type == "MESH"


def clean_object_name(name: str) -> str:
    """
    - Remove leading 'Mesh.' or 'Mesh_'
    - Keep .L / .R suffix if present at end
    - Remove trailing numeric suffix like .001
    """
    if not name:
        return "VG"

    base = name

    # 1) Remove leading Mesh. or Mesh_
    if base.startswith("Mesh."):
        base = base[len("Mesh."):]
    elif base.startswith("Mesh_"):
        base = base[len("Mesh_"):]

    # 2) Preserve side suffix
    side = ""
    if base.endswith(".L") or base.endswith(".R"):
        side = base[-2:]
        base = base[:-2]

    # 3) Remove trailing numeric suffix (.001 etc)
    if "." in base:
        head, tail = base.rsplit(".", 1)
        if tail.isdigit():
            base = head

    cleaned = (base + side).strip()
    return cleaned if cleaned else "VG"


class VGFill_Settings(PropertyGroup):
    overwrite_if_exists: BoolProperty(
        name="Overwrite if VG exists",
        description="If vertex group already exists, fill/overwrite weights to 1.0 anyway",
        default=False,
    )


class OBJECT_OT_create_vg_from_clean_name_fill_selected(Operator):
    bl_idname = "object.create_vg_from_clean_name_fill_selected"
    bl_label = "Create VG + Fill Weights"
    bl_description = "Create a vertex group from cleaned object name and fill all vertices with weight 1.0"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.vgfill_settings
        selected = context.selected_objects

        if not selected:
            self.report({"WARNING"}, "No objects selected.")
            return {"CANCELLED"}

        # Ensure we're in Object Mode for safe data access & undo behavior
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        created = 0
        filled = 0
        skipped_non_mesh = 0
        skipped_exists = 0

        for obj in selected:
            if not is_mesh_object(obj):
                skipped_non_mesh += 1
                continue

            vg_name = clean_object_name(obj.name)
            vg = obj.vertex_groups.get(vg_name)

            if vg is None:
                vg = obj.vertex_groups.new(name=vg_name)
                created += 1
            else:
                if not settings.overwrite_if_exists:
                    skipped_exists += 1
                    continue  # skip filling too, unless overwrite is enabled

            verts = obj.data.vertices
            if not verts:
                continue

            indices = [v.index for v in verts]

            # Fill all vertices with weight 1.0 in this group
            # 'REPLACE' ensures consistent full fill.
            vg.add(indices, 1.0, "REPLACE")
            filled += 1

        msg = f"Created {created} vertex groups. Filled weights on {filled} objects."
        if skipped_exists and not settings.overwrite_if_exists:
            msg += f" Skipped {skipped_exists} (VG already exists)."
        if skipped_non_mesh:
            msg += f" Skipped {skipped_non_mesh} non-mesh objects."
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class VIEW3D_PT_vg_cleanname_fill_panel(Panel):
    bl_label = "Vertex Group Tools"
    bl_idname = "VIEW3D_PT_vg_cleanname_fill_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vertex"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.vgfill_settings

        layout.prop(settings, "overwrite_if_exists")
        layout.separator()
        layout.operator(
            OBJECT_OT_create_vg_from_clean_name_fill_selected.bl_idname,
            icon="GROUP_VERTEX",
        )


classes = (
    VGFill_Settings,
    OBJECT_OT_create_vg_from_clean_name_fill_selected,
    VIEW3D_PT_vg_cleanname_fill_panel,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.vgfill_settings = PointerProperty(type=VGFill_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "vgfill_settings"):
        del bpy.types.Scene.vgfill_settings
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
