bl_info = {
    "name": "Remove All Numeric Dot Suffixes From Selected Object Names",
    "author": "ChatGPT",
    "version": (1, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar (N) > Vertex",
    "description": "Remove all '.number' patterns (e.g., .001) from selected object names (keeps .L/.R)",
    "category": "Object",
}

import bpy
import re
from bpy.types import Operator, Panel


def remove_all_numeric_dot_segments(name: str) -> str:
    """
    Remove every '.<digits>' segment anywhere in the name.
    Keep '.L' and '.R'.
    """

    if not name:
        return name

    # Protect .L and .R temporarily
    name = name.replace(".L", "__DOTL__")
    name = name.replace(".R", "__DOTR__")

    # Remove any '.digits' pattern
    name = re.sub(r"\.\d+", "", name)

    # Restore .L and .R
    name = name.replace("__DOTL__", ".L")
    name = name.replace("__DOTR__", ".R")

    return name


class OBJECT_OT_remove_all_numeric_dot_selected(Operator):
    bl_idname = "object.remove_all_numeric_dot_selected"
    bl_label = "Remove All .001 Patterns"
    bl_description = "Remove all '.number' segments from selected objects (keeps .L/.R)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected = context.selected_objects
        if not selected:
            self.report({"WARNING"}, "No objects selected.")
            return {"CANCELLED"}

        changed = 0
        unchanged = 0

        for obj in selected:
            old = obj.name
            new = remove_all_numeric_dot_segments(old)

            if new != old:
                obj.name = new
                changed += 1
            else:
                unchanged += 1

        self.report({"INFO"}, f"Renamed {changed} objects. Unchanged: {unchanged}.")
        return {"FINISHED"}


class VIEW3D_PT_remove_all_numeric_dot_panel(Panel):
    bl_label = "Object Name Tools"
    bl_idname = "VIEW3D_PT_remove_all_numeric_dot_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vertex"

    def draw(self, context):
        layout = self.layout
        layout.operator(
            OBJECT_OT_remove_all_numeric_dot_selected.bl_idname,
            icon="OUTLINER_OB_FONT"
        )


classes = (
    OBJECT_OT_remove_all_numeric_dot_selected,
    VIEW3D_PT_remove_all_numeric_dot_panel,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
