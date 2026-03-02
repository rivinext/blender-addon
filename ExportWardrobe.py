bl_info = {
    "name": "Empty Parent FBX Exporter",
    "author": "OpenAI",
    "version": (1, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Export",
    "description": "選択オブジェクトを空の子にしてFBXを書き出します",
    "category": "Import-Export",
}

import csv
import math
import os
import bpy
from bpy.props import StringProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup


def _ensure_selection(context):
    selected = [obj for obj in context.selected_objects if obj.type != 'CAMERA']
    if not selected:
        return None, "オブジェクトが選択されていません。"
    return selected, None


def _load_csv_names(csv_path):
    if not csv_path:
        return []
    filepath = bpy.path.abspath(csv_path)
    if not os.path.exists(filepath):
        return []
    names = []
    try:
        with open(filepath, newline="", encoding="utf-8") as csv_file:
            reader = csv.reader(csv_file)
            rows = list(reader)
    except (OSError, UnicodeDecodeError):
        return []
    for row in rows[1:]:
        if len(row) > 5 and row[5].strip():
            names.append(row[5].strip())
    return names


def _sync_file_name_from_csv(settings):
    names = _load_csv_names(settings.csv_path)
    if not names:
        return False
    if settings.csv_index < 0 or settings.csv_index >= len(names):
        settings.csv_index = 0
    settings.file_name = names[settings.csv_index]
    return True


def _sync_index_from_file_name(settings, names):
    current_name = settings.file_name.strip()
    if not current_name:
        return False
    try:
        settings.csv_index = names.index(current_name)
    except ValueError:
        return False
    return True


def _on_csv_path_updated(self, context):
    settings = context.scene.empty_parent_export_settings
    settings.csv_index = 0
    _sync_file_name_from_csv(settings)


def _get_all_children(obj):
    """再帰的にすべての子オブジェクトを取得"""
    children = []
    for child in obj.children:
        children.append(child)
        children.extend(_get_all_children(child))
    return children


class EmptyParentExportSettings(PropertyGroup):
    export_dir: StringProperty(
        name="出力フォルダ",
        description="FBXを書き出すフォルダを指定します",
        subtype='DIR_PATH',
    )
    csv_path: StringProperty(
        name="CSVファイル",
        description="F列の2行目以降をファイル名候補として読み込みます",
        subtype='FILE_PATH',
        update=_on_csv_path_updated,
    )
    csv_index: bpy.props.IntProperty(
        name="CSVインデックス",
        default=0,
        min=0,
        options={'HIDDEN'},
    )
    file_name: StringProperty(
        name="ファイル名",
        description="拡張子を除いたファイル名",
        default="export",
    )


class OBJECT_OT_empty_parent_fbx_export(Operator):
    bl_idname = "object.empty_parent_fbx_export"
    bl_label = "空を親にしてFBX出力"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected, error = _ensure_selection(context)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}

        settings = context.scene.empty_parent_export_settings
        if not settings.export_dir:
            self.report({'WARNING'}, "出力フォルダを指定してください。")
            return {'CANCELLED'}
        if not settings.file_name.strip():
            self.report({'WARNING'}, "ファイル名を入力してください。")
            return {'CANCELLED'}

        export_dir = bpy.path.abspath(settings.export_dir)
        filepath = bpy.path.ensure_ext(
            os.path.join(export_dir, settings.file_name),
            ".fbx",
        )

        previous_active = context.view_layer.objects.active
        previous_selection = [obj for obj in context.selected_objects]

        empty = bpy.data.objects.new(
            name=settings.file_name,
            object_data=None,
        )
        # 1. Empty生成直後に回転を設定
        empty.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        # 2. Emptyをシーンに追加
        context.collection.objects.link(empty)

        # 3. 必要ならビューを更新して依存関係を反映
        context.view_layer.update()

        # 4. 親子付けとトランスフォーム維持
        for obj in selected:
            obj.parent = empty
            obj.matrix_parent_inverse = empty.matrix_world.inverted()

        # 5. 選択状態とアクティブをEmpty+子に揃える
        for obj in context.selected_objects:
            obj.select_set(False)

        empty.select_set(True)
        for obj in selected:
            obj.select_set(True)
        context.view_layer.objects.active = empty

        # 6. 元の位置を保存して0,0,0に設定
        original_locations = {obj: obj.location.copy() for obj in selected}
        for obj in selected:
            obj.location = (0.0, 0.0, 0.0)

        try:
            bpy.ops.export_scene.fbx(
                filepath=filepath,
                use_selection=True,
                apply_unit_scale=True,
                apply_scale_options='FBX_SCALE_ALL',
                object_types={'EMPTY', 'MESH', 'ARMATURE', 'OTHER'},
            )
        finally:
            # 7. 位置を元に戻す
            for obj, location in original_locations.items():
                if obj and obj.name in context.view_layer.objects:
                    obj.location = location

        # 8. 選択状態を復元
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in previous_selection:
            if obj and obj.name in context.view_layer.objects:
                obj.select_set(True)
        if previous_active and previous_active.name in context.view_layer.objects:
            context.view_layer.objects.active = previous_active

        # 9. CSVインデックスを次に進める
        names = _load_csv_names(settings.csv_path)
        if names and _sync_index_from_file_name(settings, names):
            settings.csv_index = min(len(names) - 1, settings.csv_index + 1)
            settings.file_name = names[settings.csv_index]

        self.report({'INFO'}, f"FBXを出力しました: {filepath}")
        return {'FINISHED'}


class OBJECT_OT_parent_children_fbx_export(Operator):
    bl_idname = "object.parent_children_fbx_export"
    bl_label = "親選択: 子の位置リセットしてFBX出力"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected, error = _ensure_selection(context)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}

        # 親オブジェクトのみを対象とする
        parent_obj = selected[0] if len(selected) == 1 else None
        if not parent_obj:
            self.report({'WARNING'}, "親オブジェクトを1つだけ選択してください。")
            return {'CANCELLED'}

        settings = context.scene.empty_parent_export_settings
        if not settings.export_dir:
            self.report({'WARNING'}, "出力フォルダを指定してください。")
            return {'CANCELLED'}
        if not settings.file_name.strip():
            self.report({'WARNING'}, "ファイル名を入力してください。")
            return {'CANCELLED'}

        export_dir = bpy.path.abspath(settings.export_dir)
        filepath = bpy.path.ensure_ext(
            os.path.join(export_dir, settings.file_name),
            ".fbx",
        )

        # すべての子オブジェクトを取得
        all_children = _get_all_children(parent_obj)

        if not all_children:
            self.report({'WARNING'}, "選択された親に子オブジェクトがありません。")
            return {'CANCELLED'}

        previous_active = context.view_layer.objects.active
        previous_selection = [obj for obj in context.selected_objects]

        # 子オブジェクトの元の位置を保存
        original_locations = {obj: obj.location.copy() for obj in all_children}

        # 子オブジェクトの位置を0,0,0に設定
        for obj in all_children:
            obj.location = (0.0, 0.0, 0.0)

        # 選択を親+すべての子に設定
        for obj in context.selected_objects:
            obj.select_set(False)

        parent_obj.select_set(True)
        for obj in all_children:
            obj.select_set(True)
        context.view_layer.objects.active = parent_obj

        try:
            bpy.ops.export_scene.fbx(
                filepath=filepath,
                use_selection=True,
                apply_unit_scale=True,
                apply_scale_options='FBX_SCALE_ALL',
                object_types={'EMPTY', 'MESH', 'ARMATURE', 'OTHER'},
            )
        finally:
            # 子オブジェクトの位置を元に戻す
            for obj, location in original_locations.items():
                if obj and obj.name in context.view_layer.objects:
                    obj.location = location

        # 選択状態を復元
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in previous_selection:
            if obj and obj.name in context.view_layer.objects:
                obj.select_set(True)
        if previous_active and previous_active.name in context.view_layer.objects:
            context.view_layer.objects.active = previous_active

        # CSVインデックスを次に進める
        names = _load_csv_names(settings.csv_path)
        if names and _sync_index_from_file_name(settings, names):
            settings.csv_index = min(len(names) - 1, settings.csv_index + 1)
            settings.file_name = names[settings.csv_index]

        self.report({'INFO'}, f"FBXを出力しました (子{len(all_children)}個の位置をリセット): {filepath}")
        return {'FINISHED'}


class OBJECT_OT_empty_parent_csv_prev(Operator):
    bl_idname = "object.empty_parent_csv_prev"
    bl_label = "前へ"

    def execute(self, context):
        settings = context.scene.empty_parent_export_settings
        names = _load_csv_names(settings.csv_path)
        if not names:
            self.report({'WARNING'}, "CSVからファイル名を読み込めませんでした。")
            return {'CANCELLED'}
        _sync_index_from_file_name(settings, names)
        settings.csv_index = max(0, settings.csv_index - 1)
        settings.file_name = names[settings.csv_index]
        return {'FINISHED'}


class OBJECT_OT_empty_parent_csv_next(Operator):
    bl_idname = "object.empty_parent_csv_next"
    bl_label = "次へ"

    def execute(self, context):
        settings = context.scene.empty_parent_export_settings
        names = _load_csv_names(settings.csv_path)
        if not names:
            self.report({'WARNING'}, "CSVからファイル名を読み込めませんでした。")
            return {'CANCELLED'}
        _sync_index_from_file_name(settings, names)
        settings.csv_index = min(len(names) - 1, settings.csv_index + 1)
        settings.file_name = names[settings.csv_index]
        return {'FINISHED'}


class VIEW3D_PT_empty_parent_fbx_export(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Export'
    bl_label = '空を親にしてFBX出力'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.empty_parent_export_settings

        layout.prop(settings, "export_dir")
        layout.prop(settings, "csv_path")
        row = layout.row(align=True)
        row.operator(OBJECT_OT_empty_parent_csv_prev.bl_idname, text="Prev")
        row.operator(OBJECT_OT_empty_parent_csv_next.bl_idname, text="Next")
        layout.prop(settings, "file_name")

        layout.separator()
        layout.label(text="通常エクスポート:")
        layout.operator(OBJECT_OT_empty_parent_fbx_export.bl_idname)

        layout.separator()
        layout.label(text="親選択エクスポート:")
        layout.operator(OBJECT_OT_parent_children_fbx_export.bl_idname)


classes = (
    EmptyParentExportSettings,
    OBJECT_OT_empty_parent_fbx_export,
    OBJECT_OT_parent_children_fbx_export,
    OBJECT_OT_empty_parent_csv_prev,
    OBJECT_OT_empty_parent_csv_next,
    VIEW3D_PT_empty_parent_fbx_export,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.empty_parent_export_settings = PointerProperty(type=EmptyParentExportSettings)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.empty_parent_export_settings


if __name__ == "__main__":
    register()
