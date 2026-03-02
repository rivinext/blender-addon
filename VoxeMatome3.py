bl_info = {
    "name": "Voxel Adjust Tools - Complete",
    "author": "Your Name",
    "version": (1, 3),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Voxel Adjust",
    "description": ("OBJインポート、Merge By Distance、Pivot/Offset操作、"
                    "Vertex Group作成、均等配置機能を統合"),
    "category": "Object",
}

import bpy
import bmesh
import re
import os
from mathutils import Vector
from bpy.props import EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

# ========================================================
# 1. OBJインポート
# ========================================================

class OBJECT_OT_import_obj(bpy.types.Operator, ImportHelper):
    """OBJファイルをインポート"""
    bl_idname = "object.import_obj_one_click"
    bl_label = "Import OBJ"
    bl_description = "OBJファイルを選択してインポートします"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".obj"
    filter_glob: StringProperty(
        default="*.obj",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        if not self.filepath:
            self.report({'ERROR'}, "ファイルパスが指定されていません")
            return {'CANCELLED'}

        if not os.path.exists(self.filepath):
            self.report({'ERROR'}, f"ファイルが存在しません: {self.filepath}")
            return {'CANCELLED'}

        if not self.filepath.lower().endswith('.obj'):
            self.report({'ERROR'}, "OBJファイルを選択してください")
            return {'CANCELLED'}

        try:
            original_objects = set(context.scene.objects)
            bpy.ops.wm.obj_import(filepath=self.filepath)
            imported_objects = set(context.scene.objects) - original_objects

            if imported_objects:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in imported_objects:
                    obj.select_set(True)
                context.view_layer.objects.active = list(imported_objects)[0]
                self.report({'INFO'}, f"OBJファイルを正常にインポートしました: {os.path.basename(self.filepath)}")
            else:
                self.report({'WARNING'}, "インポートされたオブジェクトが見つかりません")

        except Exception as e:
            self.report({'ERROR'}, f"OBJファイルのインポートに失敗しました: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# ========================================================
# 2. Merge By Distance
# ========================================================

class OBJECT_OT_merge_by_distance(bpy.types.Operator):
    """選択オブジェクトにMark SharpとMerge By Distanceを実行"""
    bl_idname = "object.merge_by_distance_operator"
    bl_label = "Merge By Distance"
    bl_options = {'REGISTER', 'UNDO'}

    merge_distance: FloatProperty(
        name="Merge Distance",
        description="マージする頂点間の最大距離",
        default=0.01,
        min=0.00001,
        max=1.0,
        precision=5
    )

    def execute(self, context):
        selected_objects = context.selected_objects
        active_object = context.active_object

        if not selected_objects:
            self.report({'ERROR'}, "オブジェクトが選択されていません")
            return {'CANCELLED'}

        original_mode = context.mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for obj in selected_objects:
            if obj.type != 'MESH':
                continue

            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.mark_sharp()
            bpy.ops.mesh.remove_doubles(threshold=self.merge_distance)
            bpy.ops.object.mode_set(mode='OBJECT')

        context.view_layer.objects.active = active_object

        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=original_mode)

        self.report({'INFO'}, f"{len(selected_objects)}個のオブジェクトを処理しました")
        return {'FINISHED'}

# ========================================================
# 3. Pivot操作機能
# ========================================================

class OBJECT_OT_set_pivot_to_selection(bpy.types.Operator):
    """選択要素の中心にPivotを移動"""
    bl_idname = "object.set_pivot_to_selection_center"
    bl_label = "Pivot to Selection Center"
    bl_description = ("Edit Mode: 選択した頂点/エッジ/面の中心へ\n"
                      "Object Mode: オブジェクト中心へPivotを移動")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.object is not None and context.object.type == 'MESH')

    def execute(self, context):
        obj = context.object

        if obj.mode == 'EDIT':
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            selected_coords = []

            # 選択頂点
            selected_coords.extend([v.co for v in bm.verts if v.select])
            # 選択エッジの中点
            for edge in bm.edges:
                if edge.select:
                    edge_center = (edge.verts[0].co + edge.verts[1].co) / 2
                    selected_coords.append(edge_center)
            # 選択面の中心
            for face in bm.faces:
                if face.select:
                    face_center = face.calc_center_median()
                    selected_coords.append(face_center)

            if not selected_coords:
                bpy.ops.object.mode_set(mode='OBJECT')
                bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS', center='BOUNDS')
                bpy.ops.object.mode_set(mode='EDIT')
            else:
                center = sum(selected_coords, Vector()) / len(selected_coords)
                context.scene.cursor.location = obj.matrix_world @ center
                bpy.ops.object.mode_set(mode='OBJECT')
                bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
                bpy.ops.object.mode_set(mode='EDIT')
        else:
            # Object Mode
            selected_objects = context.selected_objects
            for obj in selected_objects:
                if obj.type == 'MESH':
                    me = obj.data
                    bm = bmesh.new()
                    bm.from_mesh(me)
                    all_coords = [v.co for v in bm.verts]

                    for edge in bm.edges:
                        edge_center = (edge.verts[0].co + edge.verts[1].co) / 2
                        all_coords.append(edge_center)

                    if all_coords:
                        center = sum(all_coords, Vector()) / len(all_coords)
                        context.scene.cursor.location = obj.matrix_world @ center
                        bpy.ops.object.select_all(action='DESELECT')
                        obj.select_set(True)
                        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
                    bm.free()

            for obj in context.selected_objects:
                obj.select_set(True)

        context.scene.cursor.location = (0, 0, 0)
        return {'FINISHED'}

class OBJECT_OT_move_pivot_to_curve_point(bpy.types.Operator):
    """選択カーブ制御点にPivotを移動"""
    bl_idname = "object.move_pivot_to_curve_point"
    bl_label = "Move Pivot to Curve Point"
    bl_description = "選択されたカーブの制御点に最も近い位置へPivotを移動"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        bpy.ops.object.mode_set(mode='OBJECT')
        selected_point = None

        for spline in obj.data.splines:
            for point in spline.bezier_points:
                if point.select_control_point:
                    selected_point = point
                    break
            if selected_point:
                break

        if selected_point:
            context.scene.cursor.location = obj.matrix_world @ selected_point.co
            context.scene.tool_settings.transform_pivot_point = 'CURSOR'
            bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
            context.scene.cursor.location = (0.0, 0.0, 0.0)

        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}

class OBJECT_OT_move_to_origin(bpy.types.Operator):
    """選択オブジェクトをワールド原点に移動"""
    bl_idname = "object.move_selected_objects_to_origin"
    bl_label = "Move to Origin"
    bl_description = "選択オブジェクトの位置をワールド原点(0,0,0)に移動"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for obj in context.selected_objects:
            obj.location = (0.0, 0.0, 0.0)
        return {'FINISHED'}

# ========================================================
# 4. Pivot極端位置設定（修正版）
# ========================================================

def set_pivot_to_extreme(obj, axis):
    """Pivotを極端な位置に設定するユーティリティ関数（修正版）"""
    # メッシュデータを取得
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)

    # 全頂点をワールド座標に変換
    world_verts = [obj.matrix_world @ v.co for v in bm.verts]

    if not world_verts:
        bm.free()
        return None

    # 軸ごとの極値を取得
    if axis == '+X':
        max_x = max(v.x for v in world_verts)
        target_verts = [v for v in world_verts if abs(v.x - max_x) < 0.0001]
    elif axis == '-X':
        min_x = min(v.x for v in world_verts)
        target_verts = [v for v in world_verts if abs(v.x - min_x) < 0.0001]
    elif axis == '+Y':
        max_y = max(v.y for v in world_verts)
        target_verts = [v for v in world_verts if abs(v.y - max_y) < 0.0001]
    elif axis == '-Y':
        min_y = min(v.y for v in world_verts)
        target_verts = [v for v in world_verts if abs(v.y - min_y) < 0.0001]
    elif axis == '+Z':
        max_z = max(v.z for v in world_verts)
        target_verts = [v for v in world_verts if abs(v.z - max_z) < 0.0001]
    elif axis == '-Z':
        min_z = min(v.z for v in world_verts)
        target_verts = [v for v in world_verts if abs(v.z - min_z) < 0.0001]
    else:
        bm.free()
        return None

    bm.free()

    # 該当する頂点の中心を計算
    if not target_verts:
        return None

    center = sum(target_verts, Vector()) / len(target_verts)

    # カーソルを移動してOriginを設定
    bpy.context.scene.cursor.location = center

    previous_selection = [o for o in bpy.context.selected_objects]
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')

    for ob in previous_selection:
        ob.select_set(True)

class OBJECT_OT_pivot_mover(bpy.types.Operator):
    """指定方向の極端な面の中心にPivotを移動"""
    bl_idname = "object.pivot_mover"
    bl_label = "Pivot Move"
    bl_description = "指定方向の極端な面の中心にPivotを移動"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(
        name="Axis",
        description="Pivotを移動する方向を選択",
        items=[
            ('+X', "+X", "極端な+Xに移動"),
            ('-X', "-X", "極端な-Xに移動"),
            ('+Y', "+Y", "極端な+Yに移動"),
            ('-Y', "-Y", "極端な-Yに移動"),
            ('+Z', "+Z", "極端な+Zに移動"),
            ('-Z', "-Z", "極端な-Zに移動"),
        ]
    )

    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_objects:
            self.report({'ERROR'}, "メッシュオブジェクトを選択してください")
            return {'CANCELLED'}

        for obj in selected_objects:
            set_pivot_to_extreme(obj, self.axis)

        bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
        self.report({'INFO'}, f"Pivotを'{self.axis}'側に移動しました")
        return {'FINISHED'}

# ========================================================
# 5. オフセット適用
# ========================================================

class OBJECT_OT_set_axis_and_move(bpy.types.Operator):
    """指定方向へオフセットを適用してPivotを移動"""
    bl_idname = "object.set_axis_and_move"
    bl_label = "Apply Offset"
    bl_description = "指定方向へオフセットを適用して原点(Pivot)を移動"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(
        name="Axis",
        description="オフセット適用方向",
        items=[
            ('+X', "+X", "正のX方向へ移動"),
            ('-X', "-X", "負のX方向へ移動"),
            ('+Y', "+Y", "正のY方向へ移動"),
            ('-Y', "-Y", "負のY方向へ移動"),
            ('+Z', "+Z", "正のZ方向へ移動"),
            ('-Z', "-Z", "負のZ方向へ移動")
        ]
    )

    def execute(self, context):
        axis = self.axis
        offset = context.scene.move_origin_offset
        selected_objects = context.selected_objects

        if not selected_objects:
            self.report({'WARNING'}, "オブジェクトが選択されていません")
            return {'CANCELLED'}

        for obj in selected_objects:
            if obj.type == 'MESH':
                context.view_layer.objects.active = obj
                original_cursor_location = context.scene.cursor.location.copy()
                origin = obj.matrix_world.translation.copy()

                if axis == '+X':
                    origin.x += offset
                elif axis == '-X':
                    origin.x -= offset
                elif axis == '+Y':
                    origin.y += offset
                elif axis == '-Y':
                    origin.y -= offset
                elif axis == '+Z':
                    origin.z += offset
                elif axis == '-Z':
                    origin.z -= offset

                context.scene.cursor.location = origin
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
                context.scene.cursor.location = original_cursor_location

        for obj in selected_objects:
            obj.select_set(True)

        self.report({'INFO'}, f"{axis}方向に{offset}mオフセットを適用しました")
        return {'FINISHED'}

# ========================================================
# 6. Vertex Group作成
# ========================================================

def sanitize_name(name):
    """オブジェクト名から番号を削除"""
    sanitized_name = re.sub(r"\.\d+$", "", name)
    return sanitized_name

class OBJECT_OT_create_vertex_groups(bpy.types.Operator):
    """オブジェクト名からVertex Groupを作成"""
    bl_idname = "object.create_vertex_groups"
    bl_label = "Create Vertex Groups"
    bl_description = "オブジェクト名からVertex Groupを作成し、全頂点を割り当てます"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not selected_objects:
            self.report({'ERROR'}, "少なくとも1つのメッシュオブジェクトを選択してください")
            return {'CANCELLED'}

        for obj in selected_objects:
            group_name = sanitize_name(obj.name)
            context.view_layer.objects.active = obj

            if group_name not in obj.vertex_groups:
                vertex_group = obj.vertex_groups.new(name=group_name)
                all_verts = [v.index for v in obj.data.vertices]
                vertex_group.add(all_verts, 1.0, 'REPLACE')
                self.report({'INFO'}, f"Vertex group '{group_name}' を作成しました")
            else:
                self.report({'INFO'}, f"Vertex group '{group_name}' は既に存在します")

        return {'FINISHED'}

# ========================================================
# 7. 均等配置
# ========================================================

class OBJECT_OT_evenly_distribute(bpy.types.Operator):
    """選択オブジェクトを最小〜最大の範囲に均等配置"""
    bl_idname = "object.evenly_distribute"
    bl_label = "Distribute (Min to Max)"
    bl_description = "選択オブジェクトを指定軸上の最小〜最大の範囲に均等配置"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(
        name="Axis",
        description="配置する軸を選択",
        items=[
            ('X', "X", "X軸に沿って均等配置"),
            ('Y', "Y", "Y軸に沿って均等配置"),
            ('Z', "Z", "Z軸に沿って均等配置"),
        ],
        default='X'
    )

    def execute(self, context):
        selected_objs = [obj for obj in context.selected_objects if obj.type in {'MESH', 'ARMATURE'}]

        if len(selected_objs) < 2:
            self.report({'WARNING'}, "2つ以上のオブジェクト(MESHまたはARMATURE)を選択してください")
            return {'CANCELLED'}

        if self.axis == 'X':
            selected_objs.sort(key=lambda o: o.location.x)
            min_val = selected_objs[0].location.x
            max_val = selected_objs[-1].location.x
        elif self.axis == 'Y':
            selected_objs.sort(key=lambda o: o.location.y)
            min_val = selected_objs[0].location.y
            max_val = selected_objs[-1].location.y
        else:
            selected_objs.sort(key=lambda o: o.location.z)
            min_val = selected_objs[0].location.z
            max_val = selected_objs[-1].location.z

        if min_val == max_val:
            self.report({'WARNING'}, "最小値と最大値が同じです。均等配置できません")
            return {'CANCELLED'}

        count = len(selected_objs)
        step = (max_val - min_val) / (count - 1)

        for i, obj in enumerate(selected_objs):
            if self.axis == 'X':
                obj.location.x = min_val + step * i
            elif self.axis == 'Y':
                obj.location.y = min_val + step * i
            else:
                obj.location.z = min_val + step * i

        return {'FINISHED'}

class OBJECT_OT_distribute_fixed_interval(bpy.types.Operator):
    """基準オブジェクトから固定間隔で選択オブジェクトを配置"""
    bl_idname = "object.distribute_fixed_interval"
    bl_label = "Distribute (Fixed Interval)"
    bl_description = "基準オブジェクトから固定間隔で選択オブジェクトを配置"
    bl_options = {'REGISTER', 'UNDO'}

    direction: EnumProperty(
        name="Direction",
        description="配置する方向を選択",
        items=[
            ('+X', "+X", "最小Xオブジェクトを基準に+X方向へ配置"),
            ('-X', "-X", "最大Xオブジェクトを基準に-X方向へ配置"),
            ('+Y', "+Y", "最小Yオブジェクトを基準に+Y方向へ配置"),
            ('-Y', "-Y", "最大Yオブジェクトを基準に-Y方向へ配置"),
            ('+Z', "+Z", "最小Zオブジェクトを基準に+Z方向へ配置"),
            ('-Z', "-Z", "最大Zオブジェクトを基準に-Z方向へ配置"),
        ],
        default='+X'
    )

    distance: FloatProperty(
        name="Interval Distance",
        description="オブジェクト間の間隔",
        default=1.0,
        min=0.0
    )

    def execute(self, context):
        selected_objs = [obj for obj in context.selected_objects if obj.type in {'MESH', 'ARMATURE'}]

        if len(selected_objs) < 2:
            self.report({'WARNING'}, "2つ以上のオブジェクト(MESHまたはARMATURE)を選択してください")
            return {'CANCELLED'}

        if self.direction == '+X':
            selected_objs.sort(key=lambda o: o.location.x)
            ref_obj_loc = selected_objs[0].location.copy()
            dir_vec = (1.0, 0.0, 0.0)
        elif self.direction == '-X':
            selected_objs.sort(key=lambda o: o.location.x, reverse=True)
            ref_obj_loc = selected_objs[0].location.copy()
            dir_vec = (-1.0, 0.0, 0.0)
        elif self.direction == '+Y':
            selected_objs.sort(key=lambda o: o.location.y)
            ref_obj_loc = selected_objs[0].location.copy()
            dir_vec = (0.0, 1.0, 0.0)
        elif self.direction == '-Y':
            selected_objs.sort(key=lambda o: o.location.y, reverse=True)
            ref_obj_loc = selected_objs[0].location.copy()
            dir_vec = (0.0, -1.0, 0.0)
        elif self.direction == '+Z':
            selected_objs.sort(key=lambda o: o.location.z)
            ref_obj_loc = selected_objs[0].location.copy()
            dir_vec = (0.0, 0.0, 1.0)
        else:  # '-Z'
            selected_objs.sort(key=lambda o: o.location.z, reverse=True)
            ref_obj_loc = selected_objs[0].location.copy()
            dir_vec = (0.0, 0.0, -1.0)

        for i, obj in enumerate(selected_objs):
            dx = dir_vec[0] * self.distance * i
            dy = dir_vec[1] * self.distance * i
            dz = dir_vec[2] * self.distance * i
            obj.location = (
                ref_obj_loc[0] + dx,
                ref_obj_loc[1] + dy,
                ref_obj_loc[2] + dz
            )

        return {'FINISHED'}

# ========================================================
# 8. UIパネル
# ========================================================

class VIEW3D_PT_voxel_adjust_tools(bpy.types.Panel):
    """Voxel Adjust Tools統合パネル"""
    bl_label = "Voxel Adjust Tools"
    bl_idname = "VIEW3D_PT_voxel_adjust_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Voxel Adjust"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # OBJインポート
        box = layout.box()
        box.label(text="OBJ Import", icon='IMPORT')
        box.operator("object.import_obj_one_click", text="Import OBJ")

        # Merge By Distance
        box = layout.box()
        box.label(text="Merge By Distance", icon='AUTOMERGE_ON')
        op = box.operator("object.merge_by_distance_operator", text="Merge By Distance")
        box.prop(op, "merge_distance", text="Distance")

        # Pivot操作
        box = layout.box()
        box.label(text="Pivot Operations", icon='PIVOT_CURSOR')
        row = box.row(align=True)
        row.operator("object.set_pivot_to_selection_center", text="To Selection")
        row.operator("object.move_pivot_to_curve_point", text="To Curve")
        box.operator("object.move_selected_objects_to_origin", text="Move to Origin")

        # Pivot Mover（極端位置）
        box = layout.box()
        box.label(text="Pivot Mover (Extreme)", icon='ORIENTATION_VIEW')
        row = box.row(align=True)
        for axis in ['+X', '-X', '+Y', '-Y', '+Z', '-Z']:
            op = row.operator("object.pivot_mover", text=axis)
            op.axis = axis

        # オフセット適用
        box = layout.box()
        box.label(text="Apply Offset", icon='EMPTY_ARROWS')
        box.prop(scene, "move_origin_offset", text="Offset (m)")
        row = box.row(align=True)
        for axis in ['+X', '-X', '+Y', '-Y', '+Z', '-Z']:
            op = row.operator("object.set_axis_and_move", text=axis)
            op.axis = axis

        # Vertex Group作成
        box = layout.box()
        box.label(text="Vertex Groups", icon='GROUP_VERTEX')
        box.operator("object.create_vertex_groups", text="Create from Object Name")

        # 均等配置
        box = layout.box()
        box.label(text="Even Distribution", icon='ARROW_LEFTRIGHT')

        # 最小〜最大
        col = box.column(align=True)
        col.label(text="Min to Max:")
        row = col.row(align=True)
        row.operator("object.evenly_distribute", text="X").axis = 'X'
        row.operator("object.evenly_distribute", text="Y").axis = 'Y'
        row.operator("object.evenly_distribute", text="Z").axis = 'Z'

        box.separator()

        # 固定間隔
        col = box.column(align=True)
        col.label(text="Fixed Interval:")
        col.prop(scene, "fixed_distribution_distance", text="Interval")
        row = col.row(align=True)
        row.operator("object.distribute_fixed_interval", text="+X").direction = '+X'
        row.operator("object.distribute_fixed_interval", text="-X").direction = '-X'
        row = col.row(align=True)
        row.operator("object.distribute_fixed_interval", text="+Y").direction = '+Y'
        row.operator("object.distribute_fixed_interval", text="-Y").direction = '-Y'
        row = col.row(align=True)
        row.operator("object.distribute_fixed_interval", text="+Z").direction = '+Z'
        row.operator("object.distribute_fixed_interval", text="-Z").direction = '-Z'

# ========================================================
# 9. 登録/登録解除
# ========================================================

classes = (
    OBJECT_OT_import_obj,
    OBJECT_OT_merge_by_distance,
    OBJECT_OT_set_pivot_to_selection,
    OBJECT_OT_move_pivot_to_curve_point,
    OBJECT_OT_move_to_origin,
    OBJECT_OT_pivot_mover,
    OBJECT_OT_set_axis_and_move,
    OBJECT_OT_create_vertex_groups,
    OBJECT_OT_evenly_distribute,
    OBJECT_OT_distribute_fixed_interval,
    VIEW3D_PT_voxel_adjust_tools,
)

def register():
    # プロパティの登録
    bpy.types.Scene.move_origin_offset = FloatProperty(
        name="Offset",
        description="Pivotを移動する距離",
        default=1.0,
        min=0.0
    )

    bpy.types.Scene.fixed_distribution_distance = FloatProperty(
        name="Distribution Distance",
        description="オブジェクト間の固定間隔",
        default=1.0,
        min=0.001
    )

    # クラスの登録
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    # プロパティの削除
    del bpy.types.Scene.move_origin_offset
    del bpy.types.Scene.fixed_distribution_distance

    # クラスの登録解除
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
