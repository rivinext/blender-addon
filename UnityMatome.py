bl_info = {
    "name": "ForUnity: Unified Suite (All-in-One)",
    "author": "rivi next + ChatGPT + Community",
    "version": (2, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > ForUnity",
    "description": "統合版: Unity連携・FBX出力・モディファイア・レンダリング・リネーム・カメラ制御など",
    "category": "Object",
}

import bpy
import os
import re
import math
from collections import deque
from contextlib import contextmanager
from mathutils import Vector

# =========================================================
# 共通ユーティリティ
# =========================================================
ADDON_ID = __name__

def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name)

def ensure_dir(path: str) -> str:
    if not path:
        return ""
    abs_path = bpy.path.abspath(path)
    os.makedirs(abs_path, exist_ok=True)
    return abs_path

def get_prefs():
    return bpy.context.preferences.addons[ADDON_ID].preferences

@contextmanager
def ensure_object_mode():
    prev = bpy.context.mode
    if prev != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except:
            pass
    try:
        yield
    finally:
        try:
            if bpy.context.mode != prev:
                bpy.ops.object.mode_set(mode=prev)
        except:
            pass

# =========================================================
# アドオン設定
# =========================================================
class FU_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    export_base_dir: bpy.props.StringProperty(
        name="デフォルト書き出し先",
        description="FBXのデフォルト書き出しフォルダ",
        subtype='DIR_PATH',
        default="//"
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "export_base_dir")

# =========================================================
# 1) ToUnity
# =========================================================
class FORUNITY_OT_to_unity(bpy.types.Operator):
    """Apply transforms for Unity export"""
    bl_idname = "forunity.to_unity"
    bl_label = "To Unity"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        orig_mode = bpy.context.mode
        orig_selected = list(context.selected_objects)
        orig_active = context.view_layer.objects.active

        targets = [obj for obj in orig_selected if obj.type == 'MESH']
        if not targets:
            self.report({'WARNING'}, "メッシュオブジェクトが選択されていません")
            return {'CANCELLED'}

        if orig_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        processed = 0
        try:
            for obj in targets:
                for o in context.selected_objects:
                    o.select_set(False)
                obj.select_set(True)
                context.view_layer.objects.active = obj

                obj.scale = (100, 100, 100)
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                obj.scale = (0.01, 0.01, 0.01)

                obj.rotation_euler[0] = math.radians(-90)
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
                obj.rotation_euler[0] = math.radians(90)

                processed += 1
        finally:
            for o in context.selected_objects:
                o.select_set(False)
            for o in orig_selected:
                o.select_set(True)
            context.view_layer.objects.active = orig_active

            if bpy.context.mode != orig_mode:
                try:
                    bpy.ops.object.mode_set(mode=orig_mode)
                except:
                    pass

        self.report({'INFO'}, f"{processed}個のメッシュオブジェクトを処理しました")
        return {'FINISHED'}

# =========================================================
# 2) Unity FBX Export
# =========================================================
class FORUNITY_OT_set_export_dir(bpy.types.Operator):
    """書き出し先フォルダを設定"""
    bl_idname = "forunity.set_export_dir"
    bl_label = "書き出し先を選ぶ"
    bl_options = {'REGISTER', 'INTERNAL'}

    directory: bpy.props.StringProperty(
        name="フォルダ",
        subtype='DIR_PATH',
        default=""
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        prefs = get_prefs()
        if not self.directory:
            self.report({'WARNING'}, "フォルダが選択されていません。")
            return {'CANCELLED'}
        prefs.export_base_dir = self.directory
        self.report({'INFO'}, f"書き出し先を設定: {prefs.export_base_dir}")
        return {'FINISHED'}

class FORUNITY_OT_export_selected_fbx(bpy.types.Operator):
    """選択オブジェクトを個別FBXで書き出し"""
    bl_idname = "forunity.export_selected_fbx"
    bl_label = "Export Selected as FBX"
    bl_options = {'REGISTER', 'UNDO'}

    include_children: bpy.props.BoolProperty(name="子オブジェクトも含める", default=True)
    include_parent_armature: bpy.props.BoolProperty(name="親アーマチュアを含める", default=True)

    def execute(self, context):
        sel = list(context.selected_objects)
        if not sel:
            self.report({'WARNING'}, "オブジェクトが選択されていません。")
            return {'CANCELLED'}

        prefs = get_prefs()
        scene = context.scene
        base_dir = ensure_dir(prefs.export_base_dir if prefs.export_base_dir else "//")
        original_active = context.view_layer.objects.active

        export_anim = scene.forunity_export_animation
        key_bones = scene.forunity_key_all_bones
        use_nla = scene.forunity_nla_strips
        use_all_actions = scene.forunity_all_actions
        force_keying = scene.forunity_force_start_end_keying
        sample_rate = scene.forunity_sampling_rate
        simplify_val = scene.forunity_simplify
        move_to_origin = getattr(scene, "forunity_export_move_to_origin", False)

        if bpy.ops.object.mode_set.poll():
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except:
                pass

        exported = 0
        for obj in sel:
            for o in context.view_layer.objects:
                o.select_set(False)

            if self.include_children:
                def _select_children(o):
                    o.select_set(True)
                    for c in o.children:
                        _select_children(c)
                _select_children(obj)
            else:
                obj.select_set(True)

            if self.include_parent_armature and obj.parent and obj.parent.type == 'ARMATURE':
                obj.parent.select_set(True)
                context.view_layer.objects.active = obj.parent
            else:
                context.view_layer.objects.active = obj

            fname = sanitize_filename(obj.name) + ".fbx"
            fpath = os.path.join(base_dir, fname)

            moved_objects = {}
            if move_to_origin:
                targets_to_move = [obj]
                if self.include_parent_armature and obj.parent and obj.parent.type == 'ARMATURE':
                    targets_to_move.append(obj.parent)

                for target in targets_to_move:
                    if target not in moved_objects:
                        moved_objects[target] = target.matrix_world.copy()
                        new_matrix = target.matrix_world.copy()
                        new_matrix.translation = Vector((0.0, 0.0, 0.0))
                        target.matrix_world = new_matrix

            try:
                bpy.ops.export_scene.fbx(
                    filepath=fpath,
                    use_selection=True,
                    add_leaf_bones=False,
                    armature_nodetype='NULL',
                    apply_unit_scale=True,
                    bake_space_transform=False,
                    object_types={'EMPTY', 'MESH', 'ARMATURE', 'LIGHT'},
                    use_mesh_modifiers=True,
                    mesh_smooth_type='FACE',
                    use_tspace=False,
                    use_custom_props=False,
                    path_mode='AUTO',
                    embed_textures=False,
                    apply_scale_options='FBX_SCALE_UNITS',
                    bake_anim=export_anim,
                    bake_anim_use_all_bones=key_bones if export_anim else True,
                    bake_anim_use_nla_strips=use_nla if export_anim else True,
                    bake_anim_use_all_actions=use_all_actions if export_anim else True,
                    bake_anim_force_startend_keying=force_keying if export_anim else True,
                    bake_anim_step=sample_rate if export_anim else 1.0,
                    bake_anim_simplify_factor=simplify_val if export_anim else 1.0,
                )
                exported += 1
            except Exception as e:
                self.report({'ERROR'}, f"{obj.name} の書き出しに失敗: {e}")
            finally:
                if move_to_origin and moved_objects:
                    for target, matrix in moved_objects.items():
                        target.matrix_world = matrix

        for o in context.view_layer.objects:
            o.select_set(False)
        for o in sel:
            o.select_set(True)
        context.view_layer.objects.active = original_active

        self.report({'INFO'}, f"FBXを書き出しました: {exported}個")
        return {'FINISHED'}

# =========================================================
# 3) Tris to Quads
# =========================================================
class FORUNITY_OT_tris_to_quads_all(bpy.types.Operator):
    """全メッシュオブジェクトにAlt+J適用"""
    bl_idname = "forunity.tris_to_quads_all"
    bl_label = "Clean Faces (Alt+J) All"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        prev_mode = context.mode
        prev_active = context.view_layer.objects.active
        bpy.ops.object.select_all(action='DESELECT')
        mesh_objs = [obj for obj in context.scene.objects if obj.type == 'MESH']

        for obj in mesh_objs:
            try:
                if obj.hide_get():
                    obj.hide_set(False)
            except:
                pass

            context.view_layer.objects.active = obj
            obj.select_set(True)

            if context.mode != 'OBJECT':
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except:
                    pass

            try:
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.tris_convert_to_quads()
            except Exception as e:
                self.report({'WARNING'}, f"{obj.name}: 処理をスキップ ({e})")
            finally:
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except:
                    pass

        bpy.ops.object.select_all(action='SELECT')
        if prev_active and prev_active.name in bpy.data.objects:
            context.view_layer.objects.active = bpy.data.objects[prev_active.name]

        if context.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except:
                pass

        self.report({'INFO'}, f"処理完了: {len(mesh_objs)}個")
        return {'FINISHED'}

# =========================================================
# 4) Modifier to Shape Keys
# =========================================================
class FORUNITY_OT_bake_modifier_to_shapekeys(bpy.types.Operator):
    """モディファイアアニメーションをシェイプキーにベイク"""
    bl_idname = "forunity.bake_modifier_to_shapekeys"
    bl_label = "Bake Modifier to Shape Keys"
    bl_options = {'REGISTER', 'UNDO'}

    frame_start: bpy.props.IntProperty(name="開始フレーム", default=1, min=0)
    frame_end: bpy.props.IntProperty(name="終了フレーム", default=120, min=0)
    frame_step: bpy.props.IntProperty(name="フレームステップ", default=1, min=1, max=10)
    apply_modifiers: bpy.props.BoolProperty(name="すべてのモディファイアを適用", default=True)

    def invoke(self, context, event):
        scene = context.scene
        self.frame_start = scene.frame_start
        self.frame_end = scene.frame_end
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "frame_start")
        layout.prop(self, "frame_end")
        layout.prop(self, "frame_step")
        layout.prop(self, "apply_modifiers")

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "メッシュオブジェクトを選択してください")
            return {'CANCELLED'}
        if not obj.modifiers:
            self.report({'WARNING'}, "モディファイアが設定されていません")
            return {'CANCELLED'}

        scene = context.scene
        original_frame = scene.frame_current
        depsgraph = context.evaluated_depsgraph_get()

        if not obj.data.shape_keys:
            obj.shape_key_add(name="Basis", from_mix=False)

        if obj.data.shape_keys:
            shape_keys_to_remove = [sk for sk in obj.data.shape_keys.key_blocks if sk.name != "Basis"]
            for sk in shape_keys_to_remove:
                obj.shape_key_remove(sk)

        created_keys = 0
        total_frames = (self.frame_end - self.frame_start) // self.frame_step + 1

        try:
            for i, frame in enumerate(range(self.frame_start, self.frame_end + 1, self.frame_step)):
                scene.frame_set(frame)
                context.view_layer.update()
                progress = (i + 1) / total_frames * 100
                print(f"ベイク中: {progress:.1f}% (Frame {frame})")

                obj_eval = obj.evaluated_get(depsgraph)
                shape_key_name = f"Frame_{frame:04d}"
                shape_key = obj.shape_key_add(name=shape_key_name, from_mix=False)
                mesh_eval = obj_eval.data

                if len(mesh_eval.vertices) != len(shape_key.data):
                    self.report({'ERROR'}, f"頂点数が一致しません(フレーム {frame})")
                    return {'CANCELLED'}

                for j, vert in enumerate(mesh_eval.vertices):
                    shape_key.data[j].co = vert.co
                created_keys += 1

            self._create_shapekey_animation(obj, self.frame_start, self.frame_end, self.frame_step)
            self.report({'INFO'}, f"{created_keys}個のシェイプキーを作成しました")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"ベイクに失敗: {e}")
            return {'CANCELLED'}
        finally:
            scene.frame_set(original_frame)

    def _create_shapekey_animation(self, obj, frame_start, frame_end, frame_step):
        if not obj.data.shape_keys:
            return
        shape_keys = obj.data.shape_keys.key_blocks
        for frame in range(frame_start, frame_end + 1, frame_step):
            shape_key_name = f"Frame_{frame:04d}"
            if shape_key_name in shape_keys:
                shape_key = shape_keys[shape_key_name]
                for sk in shape_keys:
                    if sk.name != "Basis":
                        sk.value = 0.0
                        sk.keyframe_insert(data_path="value", frame=frame)
                shape_key.value = 1.0
                shape_key.keyframe_insert(data_path="value", frame=frame)

class FORUNITY_OT_clear_baked_shapekeys(bpy.types.Operator):
    """ベイクしたシェイプキーをクリア"""
    bl_idname = "forunity.clear_baked_shapekeys"
    bl_label = "Clear Baked Shape Keys"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "メッシュオブジェクトを選択してください")
            return {'CANCELLED'}
        if not obj.data.shape_keys:
            self.report({'INFO'}, "シェイプキーがありません")
            return {'CANCELLED'}

        removed = 0
        shape_keys_to_remove = [sk for sk in obj.data.shape_keys.key_blocks
                                if sk.name.startswith("Frame_") and sk.name != "Basis"]
        for sk in shape_keys_to_remove:
            obj.shape_key_remove(sk)
            removed += 1

        self.report({'INFO'}, f"{removed}個のシェイプキーを削除しました")
        return {'FINISHED'}

# =========================================================
# 5) EEVEE Render
# =========================================================
class FORUNITY_OT_set_render_dir(bpy.types.Operator):
    """レンダリングのデフォルト出力先フォルダを設定"""
    bl_idname = "forunity.set_render_dir"
    bl_label = "デフォルト出力先を選ぶ"
    bl_options = {'REGISTER', 'INTERNAL'}

    directory: bpy.props.StringProperty(name="フォルダ", subtype='DIR_PATH', default="")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        scene = context.scene
        if not self.directory:
            self.report({'WARNING'}, "フォルダが選択されていません。")
            return {'CANCELLED'}
        scene.forunity_render_directory = self.directory
        self.report({'INFO'}, f"デフォルト出力先を設定: {self.directory}")
        return {'FINISHED'}

class FORUNITY_OT_render_eevee_png(bpy.types.Operator):
    """EEVEEでレンダリングしてRGBA PNG出力"""
    bl_idname = "forunity.render_eevee_png"
    bl_label = "Render PNG"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        prefs = get_prefs()

        # ファイル名を決定
        default_name = sanitize_filename(scene.forunity_render_filename if hasattr(scene, 'forunity_render_filename') and scene.forunity_render_filename else "render")
        if not default_name.endswith('.png'):
            default_name += '.png'

        # 出力ディレクトリを決定
        if hasattr(scene, "forunity_render_directory") and scene.forunity_render_directory:
            output_dir = bpy.path.abspath(scene.forunity_render_directory)
        else:
            output_dir = bpy.path.abspath(prefs.export_base_dir) if prefs.export_base_dir else bpy.path.abspath("//")

        # フルパスを構築
        output_path = os.path.join(output_dir, default_name)

        # ディレクトリを作成
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        original_engine = scene.render.engine
        original_filepath = scene.render.filepath
        original_file_format = scene.render.image_settings.file_format
        original_color_mode = scene.render.image_settings.color_mode
        original_film_transparent = scene.render.film_transparent

        try:
            if bpy.app.version >= (4, 0, 0):
                scene.render.engine = 'BLENDER_EEVEE_NEXT'
            else:
                scene.render.engine = 'BLENDER_EEVEE'

            scene.render.filepath = output_path
            scene.render.image_settings.file_format = 'PNG'
            scene.render.image_settings.color_mode = 'RGBA'
            scene.render.film_transparent = True
            bpy.ops.render.render(write_still=True)
            self.report({'INFO'}, f"レンダリング完了: {output_path}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"レンダリング失敗: {e}")
            return {'CANCELLED'}
        finally:
            scene.render.engine = original_engine
            scene.render.filepath = original_filepath
            scene.render.image_settings.file_format = original_file_format
            scene.render.image_settings.color_mode = original_color_mode
            scene.render.film_transparent = original_film_transparent

# =========================================================
# 6) Simple Deform Angle Key
# =========================================================
AFFECT_ONLY_MODES = {"TWIST", "BEND"}

class FU_OT_sd_angle_key_current(bpy.types.Operator):
    """Simple DeformのAngle現在値でキー挿入"""
    bl_idname = "forunity.sd_angle_key_current"
    bl_label = "Current Value"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        frame = context.scene.frame_current
        sel = [o for o in context.selected_objects if o.type == 'MESH']
        if not sel:
            self.report({'WARNING'}, "Meshオブジェクトが選択されていません")
            return {'CANCELLED'}

        applied = 0
        skipped = 0
        with ensure_object_mode():
            for obj in sel:
                context.view_layer.objects.active = obj
                for mod in obj.modifiers:
                    if mod.type != 'SIMPLE_DEFORM':
                        continue
                    if mod.deform_method not in AFFECT_ONLY_MODES:
                        skipped += 1
                        continue
                    try:
                        data_path = f'modifiers["{mod.name}"].angle'
                        obj.keyframe_insert(data_path=data_path, frame=frame)
                        applied += 1
                    except Exception as e:
                        skipped += 1

        if applied > 0:
            self.report({'INFO'}, f"キー挿入: {applied}個 @F{frame}")
        else:
            self.report({'WARNING'}, f"キーを挿入できませんでした")
        return {'FINISHED'}

class FU_OT_sd_angle_key_set(bpy.types.Operator):
    """Simple DeformのAngle値を設定してキー挿入"""
    bl_idname = "forunity.sd_angle_key_set"
    bl_label = "Set Value"
    bl_options = {'REGISTER', 'UNDO'}

    angle_value: bpy.props.FloatProperty(
        name="Angle (度)", default=0.0, soft_min=-360.0, soft_max=360.0
    )

    def execute(self, context):
        frame = context.scene.frame_current
        sel = [o for o in context.selected_objects if o.type == 'MESH']
        if not sel:
            self.report({'WARNING'}, "Meshオブジェクトが選択されていません")
            return {'CANCELLED'}

        angle_radians = math.radians(self.angle_value)
        applied = 0
        skipped = 0

        with ensure_object_mode():
            for obj in sel:
                context.view_layer.objects.active = obj
                for mod in obj.modifiers:
                    if mod.type != 'SIMPLE_DEFORM':
                        continue
                    if mod.deform_method not in AFFECT_ONLY_MODES:
                        skipped += 1
                        continue
                    try:
                        mod.angle = angle_radians
                        data_path = f'modifiers["{mod.name}"].angle'
                        obj.keyframe_insert(data_path=data_path, frame=frame)
                        applied += 1
                    except Exception as e:
                        skipped += 1

        if applied > 0:
            self.report({'INFO'}, f"キー挿入: {applied}個（{self.angle_value}°）")
        else:
            self.report({'WARNING'}, f"キーを挿入できませんでした")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

# =========================================================
# 7) Apply All Modifiers
# =========================================================
def can_apply(obj, mod):
    if obj.library or obj.override_library:
        return False, "Linked/Override object"
    if obj.type != 'MESH':
        return False, "Not a MESH"
    if obj.data.shape_keys and mod.type not in {'ARMATURE', 'DATA_TRANSFER', 'NODES'}:
        return False, "Has Shape Keys"
    return True, ""

class OBJECT_OT_apply_all_modifiers_safe(bpy.types.Operator):
    """選択オブジェクトの全Modifierを安全に一括適用"""
    bl_idname = "object.apply_all_modifiers_safe"
    bl_label = "Apply All Modifiers"
    bl_options = {'REGISTER', 'UNDO'}

    make_single_user: bpy.props.BoolProperty(name="Make Mesh Single-User", default=True)

    def execute(self, context):
        applied = 0
        skipped = []
        errors = []
        sel = [o for o in context.selected_objects]
        if not sel:
            self.report({'WARNING'}, "オブジェクトが選択されていません")
            return {'CANCELLED'}

        with ensure_object_mode():
            for obj in sel:
                if obj.type != 'MESH':
                    skipped.append((obj.name, "Not MESH"))
                    continue
                context.view_layer.objects.active = obj
                if self.make_single_user and obj.data.users > 1:
                    obj.data = obj.data.copy()
                for mod in reversed(list(obj.modifiers)):
                    ok, reason = can_apply(obj, mod)
                    if not ok:
                        skipped.append((obj.name, f"{mod.name} ({reason})"))
                        continue
                    try:
                        bpy.ops.object.modifier_apply(modifier=mod.name)
                        applied += 1
                    except RuntimeError as e:
                        errors.append(f"{obj.name}: {mod.name} -> {e}")

        msg = [f"適用: {applied}個"]
        if skipped:
            msg.append(f"スキップ: {len(skipped)}個")
        if errors:
            msg.append(f"エラー: {len(errors)}個")
        self.report({'INFO'}, " / ".join(msg))
        return {'FINISHED'}

# =========================================================
# 8) Naming Tools
# =========================================================

# 8-1) Batch Rename (Prefix/Suffix)
class OBJECT_OT_batch_rename(bpy.types.Operator):
    """選択したオブジェクトに一括でPrefix/Suffixを追加"""
    bl_idname = "object.batch_rename"
    bl_label = "Apply"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        rename_props = scene.batch_rename_props
        if not context.selected_objects:
            self.report({'WARNING'}, "オブジェクトが選択されていません")
            return {'CANCELLED'}
        if not rename_props.text:
            self.report({'WARNING'}, "追加する文字列を入力してください")
            return {'CANCELLED'}

        count = 0
        for obj in context.selected_objects:
            if rename_props.mode == 'PREFIX':
                obj.name = rename_props.text + obj.name
            else:
                obj.name = obj.name + rename_props.text
            count += 1
        self.report({'INFO'}, f"{count}個のオブジェクト名を変更しました")
        return {'FINISHED'}

class BatchRenameProperties(bpy.types.PropertyGroup):
    mode: bpy.props.EnumProperty(
        name="モード",
        items=[
            ('PREFIX', "Prefix", "名前の先頭に追加"),
            ('SUFFIX', "Suffix", "名前の末尾に追加"),
        ],
        default='PREFIX'
    )
    text: bpy.props.StringProperty(name="追加する文字列", default="")

# 8-2) Append .R/.L
def strip_side_suffix(name: str) -> str:
    if name.endswith(".R") or name.endswith(".L"):
        return name[:-2]
    return name

class OBJECT_OT_append_side_suffix(bpy.types.Operator):
    """オブジェクト名に.R/.Lを追加"""
    bl_idname = "object.append_side_suffix"
    bl_label = "Append .R/.L"
    bl_options = {"REGISTER", "UNDO"}

    side: bpy.props.EnumProperty(
        name="Side",
        items=(
            ("R", ".R", "Append .R"),
            ("L", ".L", "Append .L"),
        ),
        default="R",
    )
    replace_existing: bpy.props.BoolProperty(name="既存の.R/.Lを置換", default=True)

    def execute(self, context):
        suffix = f".{self.side}"
        renamed = 0
        for obj in context.selected_objects:
            base = obj.name
            if self.replace_existing:
                base = strip_side_suffix(base)
            if base.endswith("."):
                base = base.rstrip(".")
            new_name = base + suffix
            if obj.name != new_name:
                try:
                    obj.name = new_name
                    renamed += 1
                except Exception as e:
                    self.report({"WARNING"}, f"Failed to rename {obj.name}: {e}")
        self.report({"INFO"}, f"{renamed}個のオブジェクト名を変更")
        return {"FINISHED"}

# 8-3) Remove Numeric Suffix (.001/.002)
_NUM_SUFFIX_RE = re.compile(r"\.(\d+)$")

def strip_numeric_suffix(name: str) -> str:
    return _NUM_SUFFIX_RE.sub("", name)

class OBJECT_OT_remove_numeric_suffix(bpy.types.Operator):
    """末尾の.001/.002を削除"""
    bl_idname = "object.remove_numeric_suffix"
    bl_label = "Remove .001/.002"
    bl_options = {"REGISTER", "UNDO"}

    skip_conflicts: bpy.props.BoolProperty(name="同名がある場合はスキップ", default=True)
    include_children: bpy.props.BoolProperty(name="子オブジェクトも含める", default=False)

    def _gather_targets(self, context):
        if not self.include_children:
            return list(context.selected_objects)
        seen = set()
        queue = list(context.selected_objects)
        out = []
        while queue:
            obj = queue.pop(0)
            if obj in seen:
                continue
            seen.add(obj)
            out.append(obj)
            queue.extend(list(obj.children))
        return out

    def execute(self, context):
        targets = self._gather_targets(context)
        scene_names = {obj.name for obj in bpy.data.objects}
        renamed = 0
        skipped = 0
        unchanged = 0

        for obj in targets:
            base = strip_numeric_suffix(obj.name)
            if base == obj.name:
                unchanged += 1
                continue
            if self.skip_conflicts and base in scene_names and base != obj.name:
                skipped += 1
                continue
            try:
                obj.name = base
                renamed += 1
                scene_names.add(base)
            except Exception as e:
                self.report({"WARNING"}, f"Failed to rename {obj.name}: {e}")

        self.report({"INFO"}, f"変更: {renamed}個 / スキップ: {skipped}個")
        return {"FINISHED"}

# 8-4) Remove until 2nd Hyphen
class OBJECT_OT_remove_prefix_until_2nd_hyphen(bpy.types.Operator):
    """名前の先頭から2つ目のハイフンまで削除"""
    bl_idname = "object.remove_prefix_until_2nd_hyphen"
    bl_label = "Remove Until 2nd '-'"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            name = obj.name
            first = name.find("-")
            if first != -1:
                second = name.find("-", first + 1)
                if second != -1:
                    new_name = name[second+1:]
                    obj.name = new_name
                    count += 1
        self.report({'INFO'}, f"{count}個のオブジェクト名を変更")
        return {'FINISHED'}

# =========================================================
# 9) Empty Camera Controller
# =========================================================
class EMPTY_CAMERA_OT_move_and_adjust(bpy.types.Operator):
    """Emptyを選択オブジェクトの中心に移動＆カメラOrtho Scale調整"""
    bl_idname = "empty_camera.move_and_adjust"
    bl_label = "Move & Adjust"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.empty_camera_props
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_objects:
            self.report({'ERROR'}, "メッシュオブジェクトが選択されていません")
            return {'CANCELLED'}
        if not props.empty_object:
            self.report({'ERROR'}, "Emptyが指定されていません")
            return {'CANCELLED'}
        if not props.camera_object or props.camera_object.type != 'CAMERA':
            self.report({'ERROR'}, "カメラが指定されていません")
            return {'CANCELLED'}
        if props.camera_object.data.type != 'ORTHO':
            self.report({'ERROR'}, "カメラはOrthographicである必要があります")
            return {'CANCELLED'}

        min_coord = Vector((float('inf'), float('inf'), float('inf')))
        max_coord = Vector((float('-inf'), float('-inf'), float('-inf')))
        for obj in selected_objects:
            bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            for corner in bbox_corners:
                for i in range(3):
                    min_coord[i] = min(min_coord[i], corner[i])
                    max_coord[i] = max(max_coord[i], corner[i])

        center = (min_coord + max_coord) / 2
        z_height = max_coord.z - min_coord.z
        props.empty_object.location = center
        new_scale = z_height * props.scale_multiplier
        props.camera_object.data.ortho_scale = new_scale

        self.report({'INFO'}, f"Ortho Scale: {new_scale:.2f}")
        return {'FINISHED'}

class EMPTY_CAMERA_OT_select_empty(bpy.types.Operator):
    """アクティブオブジェクトをEmptyとして設定"""
    bl_idname = "empty_camera.select_empty"
    bl_label = "Pick"
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
    bl_label = "Pick"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.active_object and context.active_object.type == 'CAMERA':
            context.scene.empty_camera_props.camera_object = context.active_object
            self.report({'INFO'}, f"Camera: {context.active_object.name}")
        else:
            self.report({'ERROR'}, "アクティブオブジェクトがCameraではありません")
        return {'FINISHED'}

class EmptyCameraProperties(bpy.types.PropertyGroup):
    empty_object: bpy.props.PointerProperty(
        name="Empty", type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'EMPTY'
    )
    camera_object: bpy.props.PointerProperty(
        name="Camera", type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'CAMERA'
    )
    scale_multiplier: bpy.props.FloatProperty(
        name="Multiplier", default=1.2, min=0.1, max=10.0
    )

# =========================================================
# 10) Collection Visibility
# =========================================================
def get_all_target_collections_from_selection(context):
    colls = set()
    for obj in context.selected_objects:
        for c in obj.users_collection:
            colls.add(c)
    return colls

def iter_descendants(ob):
    q = deque(ob.children)
    while q:
        x = q.popleft()
        yield x
        for ch in x.children:
            q.append(ch)

def ensure_view_layer_collections_visible(context, collections):
    layer = context.view_layer.layer_collection
    def walk_layer(layer_coll):
        if layer_coll.collection in collections:
            if hasattr(layer_coll, "exclude"):
                layer_coll.exclude = False
            if hasattr(layer_coll, "holdout"):
                layer_coll.holdout = False
            if hasattr(layer_coll, "indirect_only"):
                layer_coll.indirect_only = False
        for child in layer_coll.children:
            walk_layer(child)
    walk_layer(layer)

class OBJECT_OT_hide_others_in_collection(bpy.types.Operator):
    """選択中+子孫のみ表示（同コレクション）"""
    bl_idname = "object.hide_others_in_collection"
    bl_label = "Hide Others"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.selected_objects:
            self.report({'WARNING'}, "選択オブジェクトがありません")
            return {'CANCELLED'}
        target_colls = get_all_target_collections_from_selection(context)
        if not target_colls:
            self.report({'WARNING'}, "対象コレクションが見つかりません")
            return {'CANCELLED'}

        ensure_view_layer_collections_visible(context, target_colls)
        visible_set = set()
        for sel in context.selected_objects:
            visible_set.add(sel)
            for d in iter_descendants(sel):
                visible_set.add(d)

        for coll in target_colls:
            for o in coll.objects:
                if o in visible_set:
                    try:
                        o.hide_set(False)
                    except:
                        pass
                    o.hide_render = False
                else:
                    try:
                        o.hide_set(True)
                    except:
                        pass
                    o.hide_render = True

        self.report({'INFO'}, "選択+子孫のみ表示")
        return {'FINISHED'}

class OBJECT_OT_show_all_in_selected_collections(bpy.types.Operator):
    """同コレクションの全オブジェクトを表示"""
    bl_idname = "object.show_all_in_selected_collections"
    bl_label = "Show All"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.selected_objects:
            self.report({'WARNING'}, "選択オブジェクトがありません")
            return {'CANCELLED'}
        target_colls = get_all_target_collections_from_selection(context)
        if not target_colls:
            self.report({'WARNING'}, "対象コレクションが見つかりません")
            return {'CANCELLED'}

        ensure_view_layer_collections_visible(context, target_colls)
        for coll in target_colls:
            for o in coll.objects:
                try:
                    o.hide_set(False)
                except:
                    pass
                o.hide_render = False

        self.report({'INFO'}, "全オブジェクトを表示")
        return {'FINISHED'}

# =========================================================
# UI Panel (統合版シンプルUI)
# =========================================================
class FORUNITY_PT_main_unified(bpy.types.Panel):
    """ForUnity統合パネル - シンプルUI"""
    bl_label = "ForUnity Suite"
    bl_idname = "FORUNITY_PT_main_unified"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ForUnity"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        prefs = get_prefs()

        # === 1) ToUnity & FBX Export ===
        box = layout.box()
        box.label(text="Unity Export", icon='EXPORT')
        box.operator("forunity.to_unity", text="To Unity", icon='MESH_CUBE')

        row = box.row(align=True)
        row.label(text="FBX出力先:")
        box.label(text=bpy.path.abspath(prefs.export_base_dir)[:30] + "..." if len(bpy.path.abspath(prefs.export_base_dir)) > 30 else bpy.path.abspath(prefs.export_base_dir))
        box.operator("forunity.set_export_dir", text="変更", icon='FILE_FOLDER')

        box.prop(scene, "forunity_export_animation", text="Animation")
        if hasattr(scene, "forunity_export_move_to_origin"):
            box.prop(scene, "forunity_export_move_to_origin", text="原点で書き出し")
        box.operator("forunity.export_selected_fbx", icon='EXPORT')

        # === 2) EEVEE Render ===
        box = layout.box()
        box.label(text="EEVEE Render (PNG)", icon='RENDER_STILL')
        box.prop(scene, "forunity_render_filename", text="ファイル名")

        # 出力先表示
        if hasattr(scene, "forunity_render_directory") and scene.forunity_render_directory:
            display_path = bpy.path.abspath(scene.forunity_render_directory)
        else:
            display_path = bpy.path.abspath(prefs.export_base_dir) if prefs.export_base_dir else "//"

        row = box.row(align=True)
        row.label(text="PNG出力先:")
        box.label(text=display_path[:30] + "..." if len(display_path) > 30 else display_path)
        box.operator("forunity.set_render_dir", text="変更", icon='FILE_FOLDER')
        box.operator("forunity.render_eevee_png", icon='RENDER_STILL')

        # === 3) Mesh Operations ===
        box = layout.box()
        box.label(text="Mesh Operations", icon='MESH_DATA')
        row = box.row(align=True)
        row.operator("forunity.tris_to_quads_all", icon='MOD_TRIANGULATE')
        row.operator("object.apply_all_modifiers_safe", icon='MODIFIER')

        # === 4) Modifier Bake ===
        box = layout.box()
        box.label(text="Modifier Animation Bake", icon='SHAPEKEY_DATA')
        row = box.row(align=True)
        row.operator("forunity.bake_modifier_to_shapekeys", text="Bake", icon='KEYFRAME_HLT')
        row.operator("forunity.clear_baked_shapekeys", text="Clear", icon='X')

        # === 5) Simple Deform Angle Key ===
        box = layout.box()
        box.label(text="Simple Deform Angle Key", icon='MOD_SIMPLEDEFORM')
        row = box.row(align=True)
        row.operator("forunity.sd_angle_key_current", icon='KEY_HLT')
        row.operator("forunity.sd_angle_key_set", icon='KEYTYPE_KEYFRAME_VEC')

        # === 6) Naming Tools ===
        box = layout.box()
        box.label(text="Naming Tools", icon='SORTALPHA')

        # Prefix/Suffix
        rename_props = scene.batch_rename_props
        col = box.column(align=True)
        row = col.row(align=True)
        row.prop(rename_props, "mode", expand=True)
        row = col.row(align=True)
        row.prop(rename_props, "text", text="")
        row.operator("object.batch_rename", icon='CHECKMARK')

        box.separator()

        # .R/.L
        row = box.row(align=True)
        op = row.operator("object.append_side_suffix", text=".R")
        op.side = "R"
        op = row.operator("object.append_side_suffix", text=".L")
        op.side = "L"

        # Remove suffixes
        row = box.row(align=True)
        row.operator("object.remove_numeric_suffix", icon='X')
        row.operator("object.remove_prefix_until_2nd_hyphen", icon='OUTLINER_DATA_FONT')

        # === 7) Empty Camera Controller ===
        box = layout.box()
        box.label(text="Empty Camera Controller", icon='OUTLINER_OB_EMPTY')
        props = scene.empty_camera_props

        row = box.row(align=True)
        row.prop(props, "empty_object", text="")
        row.operator("empty_camera.select_empty", icon='EYEDROPPER')

        row = box.row(align=True)
        row.prop(props, "camera_object", text="")
        row.operator("empty_camera.select_camera", icon='EYEDROPPER')

        box.prop(props, "scale_multiplier", text="Multiplier")
        box.operator("empty_camera.move_and_adjust", icon='EMPTY_ARROWS')

        # === 8) Collection Visibility ===
        box = layout.box()
        box.label(text="Collection Visibility", icon='RESTRICT_VIEW_OFF')
        row = box.row(align=True)
        row.operator("object.hide_others_in_collection", icon='HIDE_ON')
        row.operator("object.show_all_in_selected_collections", icon='RESTRICT_VIEW_OFF')

# =========================================================
# Scene Properties
# =========================================================
def register_scene_props():
    # FBX Export
    bpy.types.Scene.forunity_export_animation = bpy.props.BoolProperty(name="Animation", default=True)
    bpy.types.Scene.forunity_export_move_to_origin = bpy.props.BoolProperty(name="原点で書き出す", description="選択中のオブジェクトを一時的に原点へ移動してからFBXを書き出します", default=False)
    bpy.types.Scene.forunity_key_all_bones = bpy.props.BoolProperty(name="Key All Bones", default=True)
    bpy.types.Scene.forunity_nla_strips = bpy.props.BoolProperty(name="NLA Strips", default=True)
    bpy.types.Scene.forunity_all_actions = bpy.props.BoolProperty(name="All Actions", default=True)
    bpy.types.Scene.forunity_force_start_end_keying = bpy.props.BoolProperty(name="Force Start/End Keyframes", default=True)
    bpy.types.Scene.forunity_sampling_rate = bpy.props.FloatProperty(name="Sampling Rate", default=1.0, min=0.01, max=100.0)
    bpy.types.Scene.forunity_simplify = bpy.props.FloatProperty(name="Simplify", default=1.0, min=0.0, max=100.0)

    # Render
    bpy.types.Scene.forunity_render_filename = bpy.props.StringProperty(name="Render Filename", default="render")
    bpy.types.Scene.forunity_render_directory = bpy.props.StringProperty(name="Render Directory", subtype='DIR_PATH', default="")

    # Naming
    bpy.types.Scene.batch_rename_props = bpy.props.PointerProperty(type=BatchRenameProperties)
    bpy.types.Scene.forunity_skip_conflicts = bpy.props.BoolProperty(name="Skip if conflict", default=True)
    bpy.types.Scene.forunity_include_children = bpy.props.BoolProperty(name="Include children", default=False)

    # Empty Camera
    bpy.types.Scene.empty_camera_props = bpy.props.PointerProperty(type=EmptyCameraProperties)

def unregister_scene_props():
    del bpy.types.Scene.forunity_export_animation
    del bpy.types.Scene.forunity_export_move_to_origin
    del bpy.types.Scene.forunity_key_all_bones
    del bpy.types.Scene.forunity_nla_strips
    del bpy.types.Scene.forunity_all_actions
    del bpy.types.Scene.forunity_force_start_end_keying
    del bpy.types.Scene.forunity_sampling_rate
    del bpy.types.Scene.forunity_simplify
    del bpy.types.Scene.forunity_render_filename
    del bpy.types.Scene.forunity_render_directory
    del bpy.types.Scene.batch_rename_props
    del bpy.types.Scene.forunity_skip_conflicts
    del bpy.types.Scene.forunity_include_children
    del bpy.types.Scene.empty_camera_props

# =========================================================
# Register
# =========================================================
classes = (
    FU_AddonPreferences,
    # 1) ToUnity
    FORUNITY_OT_to_unity,
    # 2) FBX Export
    FORUNITY_OT_set_export_dir,
    FORUNITY_OT_export_selected_fbx,
    # 3) Tris to Quads
    FORUNITY_OT_tris_to_quads_all,
    # 4) Modifier Bake
    FORUNITY_OT_bake_modifier_to_shapekeys,
    FORUNITY_OT_clear_baked_shapekeys,
    # 5) Render
    FORUNITY_OT_set_render_dir,
    FORUNITY_OT_render_eevee_png,
    # 6) Simple Deform
    FU_OT_sd_angle_key_current,
    FU_OT_sd_angle_key_set,
    # 7) Apply Modifiers
    OBJECT_OT_apply_all_modifiers_safe,
    # 8) Naming Tools
    BatchRenameProperties,
    OBJECT_OT_batch_rename,
    OBJECT_OT_append_side_suffix,
    OBJECT_OT_remove_numeric_suffix,
    OBJECT_OT_remove_prefix_until_2nd_hyphen,
    # 9) Empty Camera
    EmptyCameraProperties,
    EMPTY_CAMERA_OT_move_and_adjust,
    EMPTY_CAMERA_OT_select_empty,
    EMPTY_CAMERA_OT_select_camera,
    # 10) Collection Visibility
    OBJECT_OT_hide_others_in_collection,
    OBJECT_OT_show_all_in_selected_collections,
    # Panel (統合版シンプルUI)
    FORUNITY_PT_main_unified,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    register_scene_props()

def unregister():
    unregister_scene_props()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
