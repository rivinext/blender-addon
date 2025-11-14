bl_info = {
    "name": "Empty Camera Controller",
    "author": "rivi next + ChatGPT",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > Camera Ctrl",
    "description": "Emptyを選択オブジェクトの中心に移動&カメラOrtho Scale調整",
    "category": "Object",
}

import bpy
from mathutils import Vector


# =========================================================
# Properties
# =========================================================
class EmptyCameraProperties(bpy.types.PropertyGroup):
    empty_object: bpy.props.PointerProperty(
        name="Empty",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'EMPTY'
    )
    camera_object: bpy.props.PointerProperty(
        name="Camera",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'CAMERA'
    )
    scale_multiplier: bpy.props.FloatProperty(
        name="Multiplier",
        default=1.2,
        min=0.1,
        max=10.0,
        description="Ortho Scaleの倍率調整"
    )


# =========================================================
# Operators
# =========================================================
class EMPTY_CAMERA_OT_move_and_adjust(bpy.types.Operator):
    """Emptyを選択オブジェクトの中心に移動&カメラOrtho Scale調整"""
    bl_idname = "empty_camera.move_and_adjust"
    bl_label = "Move & Adjust"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.empty_camera_props

        # 選択されたメッシュオブジェクトを取得
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_objects:
            self.report({'ERROR'}, "メッシュオブジェクトが選択されていません")
            return {'CANCELLED'}

        # Emptyチェック
        if not props.empty_object:
            self.report({'ERROR'}, "Emptyが指定されていません")
            return {'CANCELLED'}

        # カメラチェック
        if not props.camera_object or props.camera_object.type != 'CAMERA':
            self.report({'ERROR'}, "カメラが指定されていません")
            return {'CANCELLED'}

        if props.camera_object.data.type != 'ORTHO':
            self.report({'ERROR'}, "カメラはOrthographicである必要があります")
            return {'CANCELLED'}

        # 選択オブジェクトとその階層に含まれるメッシュを収集
        depsgraph = context.evaluated_depsgraph_get()
        mesh_objects = []
        seen_objects = set()

        for root_obj in selected_objects:
            for obj in (root_obj, *root_obj.children_recursive):
                if obj in seen_objects:
                    continue
                seen_objects.add(obj)
                if obj.type == 'MESH':
                    mesh_objects.append(obj)

        if not mesh_objects:
            self.report({'ERROR'}, "メッシュオブジェクトが見つかりません")
            return {'CANCELLED'}

        # 階層内の全メッシュのバウンディングボックスを計算
        min_coord = Vector((float('inf'), float('inf'), float('inf')))
        max_coord = Vector((float('-inf'), float('-inf'), float('-inf')))

        has_valid_bbox = False

        for obj in mesh_objects:
            evaluated_obj = obj.evaluated_get(depsgraph)
            evaluated_mesh = evaluated_obj.to_mesh()
            if evaluated_mesh is None:
                continue
            try:
                bbox_corners = [
                    evaluated_obj.matrix_world @ Vector(corner)
                    for corner in evaluated_mesh.bound_box
                ]
                for corner in bbox_corners:
                    for i in range(3):
                        min_coord[i] = min(min_coord[i], corner[i])
                        max_coord[i] = max(max_coord[i], corner[i])
                has_valid_bbox = True
            finally:
                evaluated_obj.to_mesh_clear()

        if not has_valid_bbox:
            self.report({'ERROR'}, "バウンディングボックスを計算できませんでした")
            return {'CANCELLED'}

        # 中心座標と各軸方向の寸法を算出
        center = (min_coord + max_coord) / 2
        bounding_dimensions = max_coord - min_coord
        max_dimension = max(bounding_dimensions.x, bounding_dimensions.y, bounding_dimensions.z)
        props.empty_object.location = center

        # カメラのOrtho Scaleを調整
        new_ortho_scale = max_dimension * props.scale_multiplier
        props.camera_object.data.ortho_scale = new_ortho_scale

        self.report(
            {'INFO'},
            f"Max Dimension: {max_dimension:.2f}, Ortho Scale: {new_ortho_scale:.2f}"
        )
        return {'FINISHED'}


class EMPTY_CAMERA_OT_select_empty(bpy.types.Operator):
    """アクティブオブジェクトをEmptyとして設定"""
    bl_idname = "empty_camera.select_empty"
    bl_label = "Pick Empty"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.active_object and context.active_object.type == 'EMPTY':
            context.scene.empty_camera_props.empty_object = context.active_object
            self.report({'INFO'}, f"Empty: {context.active_object.name}")
        else:
            self.report({'ERROR'}, "アクティブオブジェクトがEmptyではありません")
        return {'FINISHED'}


class EMPTY_CAMERA_OT_select_camera(bpy.types.Operator):
    """アクティブオブジェクトをCameraとして設定"""
    bl_idname = "empty_camera.select_camera"
    bl_label = "Pick Camera"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.active_object and context.active_object.type == 'CAMERA':
            context.scene.empty_camera_props.camera_object = context.active_object
            self.report({'INFO'}, f"Camera: {context.active_object.name}")
        else:
            self.report({'ERROR'}, "アクティブオブジェクトがCameraではありません")
        return {'FINISHED'}


# =========================================================
# UI Panel
# =========================================================
class EMPTY_CAMERA_PT_main(bpy.types.Panel):
    """Empty Camera Controllerパネル"""
    bl_label = "Empty Camera Controller"
    bl_idname = "EMPTY_CAMERA_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Camera Ctrl"

    def draw(self, context):
        layout = self.layout
        props = context.scene.empty_camera_props

        box = layout.box()
        box.label(text="Empty Camera Controller", icon='OUTLINER_OB_EMPTY')

        # Empty選択
        row = box.row(align=True)
        row.prop(props, "empty_object", text="")
        row.operator("empty_camera.select_empty", text="", icon='EYEDROPPER')

        # Camera選択
        row = box.row(align=True)
        row.prop(props, "camera_object", text="")
        row.operator("empty_camera.select_camera", text="", icon='EYEDROPPER')

        # Multiplier
        box.prop(props, "scale_multiplier", text="Multiplier")

        # 実行ボタン
        box.operator("empty_camera.move_and_adjust", icon='EMPTY_ARROWS')

        # 使い方の説明
        box = layout.box()
        box.label(text="使い方:", icon='INFO')
        col = box.column(align=True)
        col.label(text="1. EmptyとCameraを指定")
        col.label(text="2. メッシュオブジェクトを選択")
        col.label(text="3. Move & Adjustを実行")


# =========================================================
# Register
# =========================================================
classes = (
    EmptyCameraProperties,
    EMPTY_CAMERA_OT_move_and_adjust,
    EMPTY_CAMERA_OT_select_empty,
    EMPTY_CAMERA_OT_select_camera,
    EMPTY_CAMERA_PT_main,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.empty_camera_props = bpy.props.PointerProperty(type=EmptyCameraProperties)


def unregister():
    del bpy.types.Scene.empty_camera_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
