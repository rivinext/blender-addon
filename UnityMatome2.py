bl_info = {
    "name": "Empty Camera Controller",
    "author": "rivi next + ChatGPT",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > Camera Ctrl",
    "description": "Emptyを選択オブジェクトの中心に移動&カメラOrtho Scale調整",
    "category": "Object",
}

import os

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
    target_collection: bpy.props.PointerProperty(
        name="Collection",
        type=bpy.types.Collection,
        description="バッチ処理対象のコレクション"
    )
    include_children: bpy.props.BoolProperty(
        name="子孫を含める",
        default=True,
        description="各オブジェクトの子孫を含めてバウンディングボックスを算出"
    )
    output_directory: bpy.props.StringProperty(
        name="出力フォルダ",
        subtype='DIR_PATH',
        description="レンダリング画像の出力先フォルダ"
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
            bound_box = getattr(evaluated_obj, "bound_box", None)
            if not bound_box:
                continue

            bbox_corners = [
                evaluated_obj.matrix_world @ Vector(corner)
                for corner in bound_box
            ]
            for corner in bbox_corners:
                for i in range(3):
                    min_coord[i] = min(min_coord[i], corner[i])
                    max_coord[i] = max(max_coord[i], corner[i])
            has_valid_bbox = True

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


def _collect_mesh_objects(root_obj, include_children):
    """指定したオブジェクトと必要に応じて子孫からメッシュを収集"""

    if include_children:
        candidates = (root_obj, *root_obj.children_recursive)
    else:
        candidates = (root_obj,)

    meshes = []
    seen = set()
    for obj in candidates:
        if obj in seen:
            continue
        seen.add(obj)
        if obj.type == 'MESH':
            meshes.append(obj)
    return meshes


def _calculate_bounds(mesh_objects, depsgraph):
    """メッシュオブジェクト集合のワールドバウンディングボックスを算出"""

    min_coord = Vector((float('inf'), float('inf'), float('inf')))
    max_coord = Vector((float('-inf'), float('-inf'), float('-inf')))
    has_valid_bbox = False

    for obj in mesh_objects:
        evaluated_obj = obj.evaluated_get(depsgraph)
        bound_box = getattr(evaluated_obj, "bound_box", None)
        if not bound_box:
            continue

        bbox_corners = [
            evaluated_obj.matrix_world @ Vector(corner)
            for corner in bound_box
        ]
        for corner in bbox_corners:
            for i in range(3):
                min_coord[i] = min(min_coord[i], corner[i])
                max_coord[i] = max(max_coord[i], corner[i])
        has_valid_bbox = True

    if not has_valid_bbox:
        return None, None

    center = (min_coord + max_coord) / 2
    bounding_dimensions = max_coord - min_coord
    max_dimension = max(
        bounding_dimensions.x,
        bounding_dimensions.y,
        bounding_dimensions.z,
    )
    return center, max_dimension


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


class EMPTY_CAMERA_OT_batch_render(bpy.types.Operator):
    """指定コレクション内のオブジェクトを順にレンダリング"""

    bl_idname = "empty_camera.batch_render"
    bl_label = "Batch Render"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.empty_camera_props

        if not props.empty_object:
            self.report({'ERROR'}, "Emptyが指定されていません")
            return {'CANCELLED'}
        if not props.camera_object or props.camera_object.type != 'CAMERA':
            self.report({'ERROR'}, "カメラが指定されていません")
            return {'CANCELLED'}
        if props.camera_object.data.type != 'ORTHO':
            self.report({'ERROR'}, "カメラはOrthographicである必要があります")
            return {'CANCELLED'}
        if not props.target_collection:
            self.report({'ERROR'}, "ターゲットコレクションが指定されていません")
            return {'CANCELLED'}

        output_dir = bpy.path.abspath(props.output_directory) if props.output_directory else ""
        if not output_dir:
            self.report({'ERROR'}, "出力フォルダが指定されていません")
            return {'CANCELLED'}

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            self.report({'ERROR'}, f"出力フォルダを作成できません: {exc}")
            return {'CANCELLED'}

        depsgraph = context.evaluated_depsgraph_get()
        if props.include_children:
            collection_objects = set(props.target_collection.all_objects)
        else:
            collection_objects = set(props.target_collection.objects)

        target_objects = [obj for obj in props.target_collection.objects]
        if not target_objects:
            self.report({'ERROR'}, "コレクション内にオブジェクトがありません")
            return {'CANCELLED'}

        original_hide_render = {obj: obj.hide_render for obj in collection_objects}

        original_filepath = scene.render.filepath
        original_selected_names = {obj.name for obj in context.selected_objects}
        original_active = context.view_layer.objects.active

        processed = 0
        skipped = 0

        try:
            for index, obj in enumerate(target_objects, start=1):
                mesh_objects = _collect_mesh_objects(obj, props.include_children)
                if not mesh_objects:
                    skipped += 1
                    self.report({'WARNING'}, f"{obj.name}: メッシュオブジェクトがありません")
                    continue

                center, max_dimension = _calculate_bounds(mesh_objects, depsgraph)
                if center is None or max_dimension is None:
                    skipped += 1
                    self.report({'WARNING'}, f"{obj.name}: バウンディングボックスを計算できませんでした")
                    continue

                visible_objects = set(mesh_objects)
                visible_objects.add(obj)
                if props.include_children:
                    visible_objects.update(obj.children_recursive)

                for col_obj in collection_objects:
                    col_obj.hide_render = col_obj not in visible_objects

                props.empty_object.location = center
                new_ortho_scale = max_dimension * props.scale_multiplier
                props.camera_object.data.ortho_scale = new_ortho_scale

                filename = obj.name.replace("_model", "_image")
                render_path = os.path.join(output_dir, filename)
                scene.render.filepath = render_path

                self.report({'INFO'}, f"({index}/{len(target_objects)}) {obj.name}: レンダリング開始")
                try:
                    bpy.ops.render.render(write_still=True)
                except RuntimeError as exc:
                    skipped += 1
                    self.report({'ERROR'}, f"{obj.name}: レンダリングに失敗しました - {exc}")
                    continue

                processed += 1
        except Exception as exc:  # 想定外のエラー
            self.report({'ERROR'}, f"処理中にエラーが発生しました: {exc}")
            return {'CANCELLED'}
        finally:
            scene.render.filepath = original_filepath
            for obj in context.view_layer.objects:
                obj.select_set(obj.name in original_selected_names)
            if original_active and original_active.name in context.view_layer.objects:
                restored_object = context.view_layer.objects[original_active.name]
                context.view_layer.objects.active = restored_object
            else:
                context.view_layer.objects.active = None

            for obj, hide_state in original_hide_render.items():
                obj.hide_render = hide_state

        self.report({'INFO'}, f"レンダリング完了: {processed}件処理, {skipped}件スキップ")
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

        batch_box = layout.box()
        batch_box.label(text="Batch Render", icon='RENDER_STILL')
        batch_box.prop(props, "target_collection")
        batch_box.prop(props, "include_children")
        batch_box.prop(props, "output_directory")
        batch_box.label(text="※レンダリング時は対象外オブジェクトを非表示にします")
        batch_box.operator("empty_camera.batch_render", icon='RENDER_STILL')

        # 実行ボタン
        move_box = layout.box()
        move_box.operator("empty_camera.move_and_adjust", icon='EMPTY_ARROWS')

        # 使い方の説明
        box = layout.box()
        box.label(text="使い方:", icon='INFO')
        col = box.column(align=True)
        col.label(text="1. EmptyとCameraを指定")
        col.label(text="2. 個別調整: メッシュオブジェクトを選択してMove & Adjust")
        col.label(text="3. バッチ: コレクションと出力先を指定してBatch Render")


# =========================================================
# Register
# =========================================================
classes = (
    EmptyCameraProperties,
    EMPTY_CAMERA_OT_move_and_adjust,
    EMPTY_CAMERA_OT_select_empty,
    EMPTY_CAMERA_OT_select_camera,
    EMPTY_CAMERA_OT_batch_render,
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
