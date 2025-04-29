# -*- coding: utf-8 -*-
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
import os
import numpy as np
import math

from astrbot.api import logger

# --- Configuration ---
FONT_PATH_REGULAR = os.path.join(os.path.dirname(__file__), "DouyinSansBold.otf")
FONT_PATH_BOLD = os.path.join(os.path.dirname(__file__), "DouyinSansBold.otf")
LOGO_PATH = os.path.join(os.path.dirname(__file__), "astrbot_logo.jpg")

# logger.info(f"字体路径: {FONT_PATH_REGULAR}, {FONT_PATH_BOLD}")
# logger.info(f"Logo 路径: {LOGO_PATH}")

# --- File Checks ---
if not os.path.exists(FONT_PATH_REGULAR) or not os.path.exists(FONT_PATH_BOLD): logger.error("错误：字体文件未找到！");
if not os.path.exists(LOGO_PATH): logger.error(f"错误：Logo 文件 '{LOGO_PATH}' 未找到！");

# --- Style Configuration (Light Theme) ---
IMG_WIDTH = 800;
PADDING = 25
COLOR_BACKGROUND_START = (248, 250, 255);
COLOR_BACKGROUND_END = (255, 252, 248)
COLOR_SECTION_HEADER_BG = (240, 242, 248);
COLOR_CARD_BACKGROUND = (255, 255, 255)
COLOR_CARD_OUTLINE = (220, 225, 235);
COLOR_TEXT_HEADER = (0, 40, 100)
COLOR_TEXT_SUBTITLE = (80, 80, 80);
COLOR_TEXT_PLUGIN = (0, 60, 130)
COLOR_TEXT_COMMAND = (10, 70, 140);
COLOR_TEXT_DESC = (70, 70, 70)
COLOR_TEXT_FOOTER = (100, 100, 100);
COLOR_ACCENT = (0, 90, 180)
COLOR_LOGO_BG_REMOVE = (255, 255, 255);
LOGO_BG_TOLERANCE = 25

# --- Fonts ---
try:
    font_title = ImageFont.truetype(FONT_PATH_BOLD, 36);
    font_subtitle = ImageFont.truetype(FONT_PATH_REGULAR, 18)
    font_plugin_header = ImageFont.truetype(FONT_PATH_BOLD, 20);
    font_command = ImageFont.truetype(FONT_PATH_BOLD, 15)
    font_desc = ImageFont.truetype(FONT_PATH_REGULAR, 13);
    font_footer = ImageFont.truetype(FONT_PATH_REGULAR, 12)
except Exception as e:
    logger.error(f"加载字体时出错: {e}"); exit()

# --- Layout Metrics ---
TOP_AREA_HEIGHT = 120;
LOGO_TARGET_HEIGHT = 50;
SECTION_HEADER_HEIGHT = 50
SECTION_MARKER_SIZE = 18;
SECTION_MARKER_PADDING = (SECTION_HEADER_HEIGHT - SECTION_MARKER_SIZE) // 2
SECTION_TITLE_LEFT_MARGIN = SECTION_MARKER_PADDING * 2 + SECTION_MARKER_SIZE
SECTION_SPACING_BELOW_HEADER = 15;
SECTION_SPACING_AFTER_CARDS = 25
CARD_PADDING_X = 15;
CARD_PADDING_Y = 12;
CARD_SPACING = 12;
CARD_CORNER_RADIUS = 10
CARD_INTERNAL_SPACE = 4;
FOOTER_HEIGHT = 40
TALL_CARD_DESC_LENGTH_THRESHOLD = 100

# --- Input Data ---
BUILT_IN_COMMANDS_TEXT = """
[System]
/t2i : 开关文本转图片
/tts : 开关文本转语音
/sid : 获取会话 ID
/op : 管理员
/wl : 白名单
/dashboard_update : 更新管理面板(op)
/alter_cmd : 设置指令权限(op)

[大模型]
/provider : 大模型提供商
/model : 模型列表
/ls : 对话列表
/new : 创建新对话
/switch 序号 : 切换对话
/rename 新名字 : 重命名当前对话
/del : 删除当前会话对话(op)
/reset : 重置 LLM 会话(op)
/history : 当前对话的对话记录
/persona : 人格情景(op)
/tool ls : 函数工具
/key : API Key(op)
/websearch : 网页搜索
"""


# --- Helper Functions ---
def parse_single_command_list(text_list):
    # Code from previous correct version
    commands_list = [];
    last_command = None;
    processed_lines = []
    if isinstance(text_list, str):
        lines_raw = text_list.strip().splitlines()
        for line in lines_raw:
            stripped = line.strip()
            if not stripped: continue
            if stripped.startswith('[') and stripped.endswith(']'): continue
            processed_lines.append(line)
    elif isinstance(text_list, list):
        processed_lines = text_list
    for line in processed_lines:
        stripped_line = line.strip();
        if not stripped_line: continue
        is_continuation = (line.startswith('  ') or line.startswith('\t'))
        if is_continuation and last_command and commands_list:
            cmd, desc = commands_list[-1];
            current_desc = desc if desc is not None else ""
            prefix = "\n" if not line.startswith((' ', '\t')) else "\n";
            commands_list[-1] = (cmd, current_desc + prefix + line.lstrip());
            continue
        last_command = None;
        parts = [];
        sep_found = None
        if ' : ' in stripped_line:
            parts = stripped_line.split(' : ', 1); sep_found = ' : '
        elif ' # ' in stripped_line:
            parts = stripped_line.split(' # ', 1); sep_found = ' # '
        elif '#' in stripped_line and not stripped_line.startswith('#'):
            parts = stripped_line.split('#', 1); sep_found = '#'
        elif ':' in stripped_line and not stripped_line.startswith(':'):
            parts = stripped_line.split(':', 1); sep_found = ':'
        command = None;
        description = None
        if len(parts) == 2 and sep_found:
            cmd_part = parts[0]
            if cmd_part.startswith('- '):
                command = cmd_part[2:].strip()
            else:
                command = cmd_part.strip()
            description = parts[1].strip()
        else:
            cmd_part = stripped_line
            if cmd_part.startswith('- '):
                command = cmd_part[2:].strip()
            else:
                command = cmd_part.strip()
            description = None
        if command:
            if description is not None and not description: description = None
            commands_list.append((command, description));
            last_command = command
    cleaned_list = []
    for cmd, desc in commands_list:
        # 只取描述的第一行
        if desc and '\n' in desc:
            desc = desc.split('\n')[0].strip()
        cleaned_list.append((cmd, desc.strip() if desc else None))
    return cleaned_list


def parse_plugin_commands_sorted_grouped(plugin_dict):
    built_in_plugin = None;
    large_plugins = [];
    small_plugins = []
    built_in_commands_list = parse_single_command_list(BUILT_IN_COMMANDS_TEXT)
    if built_in_commands_list: built_in_plugin = ("内置指令", built_in_commands_list)
    for plugin_name, command_list_raw in plugin_dict.items():
        # 移除对 astrbot 开头插件的过滤
        if plugin_name == "内置指令" or not command_list_raw: continue
        plugin_commands = parse_single_command_list(command_list_raw)
        if plugin_commands:
            count = len(plugin_commands)
            if count == 1:
                small_plugins.append((plugin_name, plugin_commands))
            elif count >= 2:
                large_plugins.append((plugin_name, plugin_commands))
    large_plugins.sort(key=lambda item: len(item[1]), reverse=True)
    grouped_small_plugin = None
    if small_plugins:
        all_small_commands = [];
        [all_small_commands.extend(cmds) for name, cmds in small_plugins]
        if all_small_commands: grouped_small_plugin = ("简易指令", all_small_commands); logger.info(
            f"-> 创建 '简易指令' ({len(all_small_commands)} 条)")
    final_plugin_data = []
    if built_in_plugin: final_plugin_data.append(built_in_plugin)
    final_plugin_data.extend(large_plugins)
    if grouped_small_plugin: final_plugin_data.append(grouped_small_plugin)
    # print("最终插件绘制顺序:", [p[0] for p in final_plugin_data])
    return final_plugin_data


def draw_gradient(draw, width, height, color_start, color_end):
    for y in range(height): ratio = y / float(height); r = int(
        color_start[0] * (1 - ratio) + color_end[0] * ratio); g = int(
        color_start[1] * (1 - ratio) + color_end[1] * ratio); b = int(
        color_start[2] * (1 - ratio) + color_end[2] * ratio); draw.line([(0, y), (width, y)], fill=(r, g, b))


def get_text_metrics(text, font, draw):
    if not text: return (0, 0, 0, 0), (0, 0)
    try:
        bbox = draw.textbbox((0, 0), text, font=font); width = bbox[2] - bbox[0]; height = bbox[3] - bbox[
            1]; return bbox, (width, height)
    except AttributeError:
        width = draw.textlength(text, font=font); metrics = font.getmetrics(); height = metrics[0] + metrics[1] if sum(
            metrics) > 0 else font.size * 1.2; return (0, 0, width, height), (width, height)
    except Exception:
        est_h = font.size * 1.2; est_w = len(text) * font.size * 0.6; return (
        0, 0, max(1, int(est_w)), max(1, int(est_h))), (max(1, int(est_w)), max(1, int(est_h)))


def draw_rounded_rectangle(draw, xy, radius, fill=None, outline=None, width=1):
    x1, y1, x2, y2 = xy;
    if x1 >= x2 or y1 >= y2: return; radius = min(radius, (x2 - x1) // 2, (y2 - y1) // 2)
    if fill: draw.rectangle((x1 + radius, y1, x2 - radius, y2), fill=fill); draw.rectangle(
        (x1, y1 + radius, x2, y2 - radius), fill=fill); draw.pieslice((x1, y1, x1 + 2 * radius, y1 + 2 * radius), 180,
                                                                      270, fill=fill); draw.pieslice(
        (x2 - 2 * radius, y1, x2, y1 + 2 * radius), 270, 360, fill=fill); draw.pieslice(
        (x1, y2 - 2 * radius, x1 + 2 * radius, y2), 90, 180, fill=fill); draw.pieslice(
        (x2 - 2 * radius, y2 - 2 * radius, x2, y2), 0, 90, fill=fill)
    if outline and width > 0: draw.arc((x1, y1, x1 + 2 * radius, y1 + 2 * radius), 180, 270, fill=outline,
                                       width=width); draw.arc((x2 - 2 * radius, y1, x2, y1 + 2 * radius), 270, 360,
                                                              fill=outline, width=width); draw.arc(
        (x1, y2 - 2 * radius, x1 + 2 * radius, y2), 90, 180, fill=outline, width=width); draw.arc(
        (x2 - 2 * radius, y2 - 2 * radius, x2, y2), 0, 90, fill=outline, width=width); draw.line(
        [(x1 + radius, y1), (x2 - radius, y1)], fill=outline, width=width); draw.line(
        [(x1 + radius, y2), (x2 - radius, y2)], fill=outline, width=width); draw.line(
        [(x1, y1 + radius), (x1, y2 - radius)], fill=outline, width=width); draw.line(
        [(x2, y1 + radius), (x2, y2 - radius)], fill=outline, width=width)


def calculate_card_content_height(command, description, card_inner_width, draw):
    cmd_h = 0;
    desc_h = 0;
    space = 0;
    card_inner_width = max(1, card_inner_width)
    if command: _bbox, (_w, cmd_h) = get_text_metrics(command, font_command, draw); cmd_h = max(1, cmd_h)
    if description:
        # 只取描述的第一行
        if '\n' in description:
            description = description.split('\n')[0].strip()

        avg_char_width_bbox, (avg_w, avg_h) = get_text_metrics("A", font_desc, draw);
        avg_char_width = avg_w if avg_w > 0 else font_desc.size * 0.6
        wrap_width_chars = 10
        if avg_char_width > 0: wrap_width_chars = max(10, int(card_inner_width / avg_char_width * 0.95))
        desc_lines = textwrap.wrap(description, width=wrap_width_chars, replace_whitespace=False, drop_whitespace=False,
                                   break_long_words=True)
        desc_internal_spacing = 1
        for i, line in enumerate(desc_lines):
            _bbox_line, (_w_line, line_h) = get_text_metrics(line, font_desc, draw);
            desc_h += max(1, line_h)
            if i < len(desc_lines) - 1: desc_h += desc_internal_spacing
    if cmd_h > 0 and desc_h > 0: space = CARD_INTERNAL_SPACE
    total_content_height = cmd_h + space + desc_h
    return total_content_height


# --- Logo Loading ---
try:
    logo_img_original = Image.open(LOGO_PATH).convert("RGBA");
    img_data = np.array(logo_img_original);
    r, g, b, a = img_data.T
    white_areas = (r >= COLOR_LOGO_BG_REMOVE[0] - LOGO_BG_TOLERANCE) & (
                g >= COLOR_LOGO_BG_REMOVE[1] - LOGO_BG_TOLERANCE) & (
                              b >= COLOR_LOGO_BG_REMOVE[2] - LOGO_BG_TOLERANCE) & (a > 128)
    img_data[..., -1][white_areas.T] = 0;
    logo_transparent_bg = Image.fromarray(img_data);
    original_width, original_height = logo_transparent_bg.size;
    aspect_ratio = original_width / original_height
    new_logo_width = int(LOGO_TARGET_HEIGHT * aspect_ratio);
    resized_logo = logo_transparent_bg.resize((new_logo_width, LOGO_TARGET_HEIGHT), Image.Resampling.LANCZOS);
    # print(f"Logo 调整大小为 {resized_logo.size}")
except Exception as e:
    logger.warning(f"加载或处理 Logo 时出错: {e}"); resized_logo = None

# --- Main Execution ---
def draw_help_image(command_data):
    plugins_data = parse_plugin_commands_sorted_grouped(command_data)
    if not plugins_data: logger.warning("错误：没有解析到任何有效的插件或命令。"); exit()
    draw_temp = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    # print("开始计算图片高度...")
    current_y = PADDING + TOP_AREA_HEIGHT
    available_width_for_cards = IMG_WIDTH - PADDING * 2

    # --- Height Calculation (Pass 1) ---
    for plugin_index, (plugin_name, commands) in enumerate(plugins_data):
        current_y += SECTION_HEADER_HEIGHT + SECTION_SPACING_BELOW_HEADER
        cards_info = []  # 存储每个卡片的信息，用于更智能地布局

        # 预计算每个卡片的宽度和高度
        if commands:
            # 基础卡片设置
            max_cards_per_row = 4  # 每行最多放置的卡片数
            std_card_width = (available_width_for_cards - (max_cards_per_row - 1) * CARD_SPACING) / max_cards_per_row
            std_card_inner_width = max(50, std_card_width - CARD_PADDING_X * 2)
            double_card_width = min(available_width_for_cards, std_card_width * 2 + CARD_SPACING)
            double_card_inner_width = max(50, double_card_width - CARD_PADDING_X * 2)

            # 计算每个卡片的尺寸
            for i, (cmd, desc) in enumerate(commands):
                # 只取描述的第一行
                if desc and '\n' in desc:
                    desc = desc.split('\n')[0].strip()

                is_tall = (desc is not None and len(desc) > TALL_CARD_DESC_LENGTH_THRESHOLD)
                if is_tall:
                    card_w = double_card_width
                    card_inner_w = double_card_inner_width
                    # 使用双宽卡片
                    size_category = "double"  # 双宽卡片
                else:
                    card_w = std_card_width
                    card_inner_w = std_card_inner_width
                    size_category = "standard"  # 标准卡片

                content_h = calculate_card_content_height(cmd, desc, card_inner_w, draw_temp)
                card_h = content_h + CARD_PADDING_Y * 2

                # 增加描述长度属性
                desc_length = len(desc) if desc else 0

                cards_info.append({
                    "index": i,
                    "cmd": cmd,
                    "desc": desc,
                    "desc_length": desc_length,  # 描述长度属性
                    "width": card_w,
                    "height": card_h,
                    "inner_width": card_inner_w,
                    "category": size_category
                })

            # 更智能地排序卡片 - 针对更高效的布局
            # 首先处理双宽卡片，然后用描述长度优先算法处理剩余卡片
            double_cards = [card for card in cards_info if card["category"] == "double"]
            standard_cards = [card for card in cards_info if card["category"] == "standard"]

            # 按描述长度排序标准卡片（短的在前面）
            standard_cards.sort(key=lambda x: x["desc_length"])

            # 把卡片放入行中 - 使用更智能的算法来减少空白
            rows = []
            current_row = {"cards": [], "width_used": 0, "max_height": 0}

            # 首先放置所有双宽卡片 - 每个都独占一行
            for card in double_cards:
                rows.append({"cards": [card], "width_used": card["width"], "max_height": card["height"]})

            # 然后使用更高效的算法放置标准卡片
            for card in standard_cards:
                # 尝试将卡片添加到当前行
                if current_row["width_used"] + card["width"] + CARD_SPACING <= available_width_for_cards:
                    # 当前行还有空间
                    if current_row["width_used"] > 0:  # 如果不是行的第一个卡片，添加间距
                        current_row["width_used"] += CARD_SPACING
                    current_row["cards"].append(card)
                    current_row["width_used"] += card["width"]
                    current_row["max_height"] = max(current_row["max_height"], card["height"])
                else:
                    # 当前行没有足够空间，创建新行
                    if current_row["cards"]:  # 如果当前行有卡片，保存它
                        rows.append(current_row)
                    current_row = {"cards": [card], "width_used": card["width"], "max_height": card["height"]}

            # 添加最后一行（如果有卡片）
            if current_row["cards"]:
                rows.append(current_row)

            # 根据行信息计算总高度
            for row in rows:
                current_y += row["max_height"] + CARD_SPACING

            # 减去最后一行之后的额外空间
            current_y -= CARD_SPACING

        current_y += SECTION_SPACING_AFTER_CARDS

    total_height = current_y + FOOTER_HEIGHT
    total_height = int(math.ceil(total_height))
    # print(f"计算出的图片高度: {total_height}")

    # --- Pass 2: Create Image and Draw ---
    img = Image.new('RGB', (IMG_WIDTH, total_height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw_gradient(draw, IMG_WIDTH, total_height, COLOR_BACKGROUND_START, COLOR_BACKGROUND_END)

    # --- Draw Top Area ---
    current_y = PADDING
    if resized_logo:
        logo_x = PADDING
        logo_y = current_y + (TOP_AREA_HEIGHT - PADDING - resized_logo.height) // 2
        try:
            img.paste(resized_logo, (logo_x, logo_y), mask=resized_logo)
        except Exception as e:
            logger.warning(f"粘贴 Logo 失败 (尝试带透明度): {e}")
            try:
                img.paste(resized_logo.convert("RGB"), (logo_x, logo_y))
                logger.warning("警告: Logo 作为不透明图像粘贴 (因透明度粘贴失败)")
            except Exception as e2:
                logger.warning(f"Logo 回退粘贴也失败: {e2}")
    title_x = PADDING + (resized_logo.width + 20 if resized_logo else 0)
    _bbox_title, (title_w, title_h) = get_text_metrics("AstrBot 命令帮助", font_title, draw)
    _bbox_sub, (sub_w, sub_h) = get_text_metrics("可用插件及指令列表", font_subtitle, draw)
    title_y = current_y + (TOP_AREA_HEIGHT - PADDING - title_h - sub_h - 5) // 2
    draw.text((title_x, title_y), "AstrBot 命令帮助", font=font_title, fill=COLOR_TEXT_HEADER)
    draw.text((title_x, title_y + title_h + 5), "可用插件及指令列表", font=font_subtitle, fill=COLOR_TEXT_SUBTITLE)
    current_y += TOP_AREA_HEIGHT

    # --- 改进的绘制部分 ---
    for plugin_index, (plugin_name, commands) in enumerate(plugins_data):
        # 绘制插件标题栏
        header_y = current_y
        draw.rectangle((0, header_y, IMG_WIDTH, header_y + SECTION_HEADER_HEIGHT), fill=COLOR_SECTION_HEADER_BG)
        marker_x = PADDING + SECTION_MARKER_PADDING
        marker_y = header_y + SECTION_MARKER_PADDING
        draw.rectangle((marker_x, marker_y, marker_x + SECTION_MARKER_SIZE, marker_y + SECTION_MARKER_SIZE),
                       fill=COLOR_ACCENT)
        _bbox_p, (p_w, p_h) = get_text_metrics(plugin_name, font_plugin_header, draw)
        title_py = header_y + (SECTION_HEADER_HEIGHT - p_h) // 2
        draw.text((PADDING + SECTION_TITLE_LEFT_MARGIN, title_py), plugin_name, font=font_plugin_header,
                  fill=COLOR_TEXT_PLUGIN)
        current_y += SECTION_HEADER_HEIGHT + SECTION_SPACING_BELOW_HEADER

        if commands:
            # 修改：优先处理长描述卡片和预计算所有卡片宽高
            cards_info = []
            max_cards_per_row = 4
            std_card_width = (available_width_for_cards - (max_cards_per_row - 1) * CARD_SPACING) / max_cards_per_row
            std_card_inner_width = max(50, std_card_width - CARD_PADDING_X * 2)
            double_card_width = min(available_width_for_cards, std_card_width * 2 + CARD_SPACING)
            double_card_inner_width = max(50, double_card_width - CARD_PADDING_X * 2)

            # 预计算每个卡片的尺寸和类型
            for i, (cmd, desc) in enumerate(commands):
                # 只取描述的第一行
                if desc and '\n' in desc:
                    desc = desc.split('\n')[0].strip()

                is_tall = (desc is not None and len(desc) > TALL_CARD_DESC_LENGTH_THRESHOLD)
                if is_tall:
                    card_w = double_card_width
                    card_inner_w = double_card_inner_width
                    size_category = "double"
                else:
                    card_w = std_card_width
                    card_inner_w = std_card_inner_width
                    size_category = "standard"

                content_h = calculate_card_content_height(cmd, desc, card_inner_w, draw)
                card_h = content_h + CARD_PADDING_Y * 2

                # 增加描述长度属性
                desc_length = len(desc) if desc else 0

                cards_info.append({
                    "index": i,
                    "cmd": cmd,
                    "desc": desc,
                    "desc_length": desc_length,
                    "width": card_w,
                    "height": card_h,
                    "inner_width": card_inner_w,
                    "category": size_category
                })

                # 分离双宽卡片和标准卡片
            double_cards = [card for card in cards_info if card["category"] == "double"]
            standard_cards = [card for card in cards_info if card["category"] == "standard"]

            # 按描述长度排序标准卡片（描述少的在前面）
            standard_cards.sort(key=lambda x: x["desc_length"])

            # 先处理双宽卡片 - 每个独占一行
            for card in double_cards:
                cmd = card["cmd"]
                desc = card["desc"]
                card_w = card["width"]
                card_h = card["height"]
                card_inner_w = card["inner_width"]

                # 绘制双宽卡片 - 每个独占一行
                card_x = PADDING
                card_rect = (card_x, current_y, card_x + card_w, current_y + card_h)
                draw_rounded_rectangle(draw, card_rect, CARD_CORNER_RADIUS,
                                       fill=COLOR_CARD_BACKGROUND, outline=COLOR_CARD_OUTLINE, width=1)

                # 绘制卡片内容
                content_x = card_x + CARD_PADDING_X
                content_y = current_y + CARD_PADDING_Y
                draw.text((content_x, content_y), cmd, font=font_command, fill=COLOR_TEXT_COMMAND)

                if desc:
                    # 计算描述文本位置
                    cmd_bbox, (cmd_w, cmd_h) = get_text_metrics(cmd, font_command, draw)
                    desc_y = content_y + cmd_h + CARD_INTERNAL_SPACE

                    # 文本自动换行
                    avg_char_width_bbox, (avg_w, avg_h) = get_text_metrics("A", font_desc, draw)
                    avg_char_width = avg_w if avg_w > 0 else font_desc.size * 0.6
                    wrap_width_chars = max(10, int(card_inner_w / avg_char_width * 0.95))

                    # 确保只取第一行
                    if '\n' in desc:
                        desc = desc.split('\n')[0].strip()

                    desc_lines = textwrap.wrap(desc, width=wrap_width_chars,
                                               replace_whitespace=False,
                                               drop_whitespace=False,
                                               break_long_words=True)

                    # 绘制描述文本
                    line_y = desc_y
                    desc_internal_spacing = 1
                    for line in desc_lines:
                        draw.text((content_x, line_y), line, font=font_desc, fill=COLOR_TEXT_DESC)
                        _bbox_line, (_w_line, line_h) = get_text_metrics(line, font_desc, draw)
                        line_y += line_h + desc_internal_spacing

                # 更新垂直位置
                current_y += card_h + CARD_SPACING

            # 处理标准卡片，使用更高效的行填充算法
            current_row_cards = []
            current_row_width = 0
            current_row_start_y = current_y
            max_height_in_row = 0

            for card in standard_cards:
                cmd = card["cmd"]
                desc = card["desc"]
                card_w = card["width"]
                card_h = card["height"]
                card_inner_w = card["inner_width"]

                # 检查当前行是否还有足够空间
                new_width = current_row_width + card_w
                if current_row_width > 0:  # 如果不是行的第一个卡片，需要考虑间距
                    new_width += CARD_SPACING

                # 如果这个卡片放不下，开始新的一行
                if new_width > available_width_for_cards and current_row_cards:
                    # 绘制当前行的所有卡片
                    card_x = PADDING
                    for row_card in current_row_cards:
                        row_cmd = row_card["cmd"]
                        row_desc = row_card["desc"]
                        row_card_w = row_card["width"]
                        row_card_h = row_card["height"]
                        row_card_inner_w = row_card["inner_width"]

                        # 垂直居中对齐行中的卡片
                        y_offset = (max_height_in_row - row_card_h) // 2
                        card_y = current_row_start_y + y_offset

                        # 绘制卡片背景
                        card_rect = (card_x, card_y, card_x + row_card_w, card_y + row_card_h)
                        draw_rounded_rectangle(draw, card_rect, CARD_CORNER_RADIUS,
                                               fill=COLOR_CARD_BACKGROUND, outline=COLOR_CARD_OUTLINE, width=1)

                        # 绘制卡片内容
                        content_x = card_x + CARD_PADDING_X
                        content_y = card_y + CARD_PADDING_Y
                        draw.text((content_x, content_y), row_cmd, font=font_command, fill=COLOR_TEXT_COMMAND)

                        if row_desc:
                            # 计算描述文本位置
                            cmd_bbox, (cmd_w, cmd_h) = get_text_metrics(row_cmd, font_command, draw)
                            desc_y = content_y + cmd_h + CARD_INTERNAL_SPACE

                            # 文本自动换行
                            avg_char_width_bbox, (avg_w, avg_h) = get_text_metrics("A", font_desc, draw)
                            avg_char_width = avg_w if avg_w > 0 else font_desc.size * 0.6
                            wrap_width_chars = max(10, int(row_card_inner_w / avg_char_width * 0.95))

                            # 确保只取第一行
                            if '\n' in row_desc:
                                row_desc = row_desc.split('\n')[0].strip()

                            desc_lines = textwrap.wrap(row_desc, width=wrap_width_chars,
                                                       replace_whitespace=False,
                                                       drop_whitespace=False,
                                                       break_long_words=True)

                            # 绘制描述文本
                            line_y = desc_y
                            desc_internal_spacing = 1
                            for line in desc_lines:
                                draw.text((content_x, line_y), line, font=font_desc, fill=COLOR_TEXT_DESC)
                                _bbox_line, (_w_line, line_h) = get_text_metrics(line, font_desc, draw)
                                line_y += line_h + desc_internal_spacing

                        # 更新水平位置
                        card_x += row_card_w + CARD_SPACING

                    # 更新垂直位置到下一行开始
                    current_y = current_row_start_y + max_height_in_row + CARD_SPACING
                    current_row_start_y = current_y
                    current_row_cards = []
                    current_row_width = 0
                    max_height_in_row = 0

                # 添加当前卡片到行
                current_row_cards.append(card)
                if current_row_width > 0:  # 如果不是行的第一个卡片，添加间距
                    current_row_width += CARD_SPACING
                current_row_width += card_w
                max_height_in_row = max(max_height_in_row, card_h)

            # 绘制最后一行的卡片（如果有）
            if current_row_cards:
                card_x = PADDING
                for row_card in current_row_cards:
                    row_cmd = row_card["cmd"]
                    row_desc = row_card["desc"]
                    row_card_w = row_card["width"]
                    row_card_h = row_card["height"]
                    row_card_inner_w = row_card["inner_width"]

                    # 垂直居中对齐行中的卡片
                    y_offset = (max_height_in_row - row_card_h) // 2
                    card_y = current_row_start_y + y_offset

                    # 绘制卡片背景
                    card_rect = (card_x, card_y, card_x + row_card_w, card_y + row_card_h)
                    draw_rounded_rectangle(draw, card_rect, CARD_CORNER_RADIUS,
                                           fill=COLOR_CARD_BACKGROUND, outline=COLOR_CARD_OUTLINE, width=1)

                    # 绘制卡片内容
                    content_x = card_x + CARD_PADDING_X
                    content_y = card_y + CARD_PADDING_Y
                    draw.text((content_x, content_y), row_cmd, font=font_command, fill=COLOR_TEXT_COMMAND)

                    if row_desc:
                        # 计算描述文本位置
                        cmd_bbox, (cmd_w, cmd_h) = get_text_metrics(row_cmd, font_command, draw)
                        desc_y = content_y + cmd_h + CARD_INTERNAL_SPACE

                        # 文本自动换行
                        avg_char_width_bbox, (avg_w, avg_h) = get_text_metrics("A", font_desc, draw)
                        avg_char_width = avg_w if avg_w > 0 else font_desc.size * 0.6
                        wrap_width_chars = max(10, int(row_card_inner_w / avg_char_width * 0.95))

                        # 确保只取第一行
                        if '\n' in row_desc:
                            row_desc = row_desc.split('\n')[0].strip()

                        desc_lines = textwrap.wrap(row_desc, width=wrap_width_chars,
                                                   replace_whitespace=False,
                                                   drop_whitespace=False,
                                                   break_long_words=True)

                        # 绘制描述文本
                        line_y = desc_y
                        desc_internal_spacing = 1
                        for line in desc_lines:
                            draw.text((content_x, line_y), line, font=font_desc, fill=COLOR_TEXT_DESC)
                            _bbox_line, (_w_line, line_h) = get_text_metrics(line, font_desc, draw)
                            line_y += line_h + desc_internal_spacing

                    # 更新水平位置
                    card_x += row_card_w + CARD_SPACING

                # 更新垂直位置
                current_y = current_row_start_y + max_height_in_row + CARD_SPACING

            # 为下一个章节添加间距
        current_y += SECTION_SPACING_AFTER_CARDS - CARD_SPACING  # 减去多余的卡片间距

    # --- Draw Footer ---
    footer_y = total_height - FOOTER_HEIGHT
    draw.rectangle((0, footer_y, IMG_WIDTH, total_height), fill=(245, 247, 250))
    footer_text = "Power by AstrBot & Created By astrbot_plugin_help"
    _bbox_footer, (footer_w, footer_h) = get_text_metrics(footer_text, font_footer, draw)
    footer_text_x = (IMG_WIDTH - footer_w) // 2  # 水平居中
    footer_text_y = footer_y + (FOOTER_HEIGHT - footer_h) // 2  # 垂直居中
    # 绘制居中文本
    draw.text((footer_text_x, footer_text_y), footer_text, font=font_footer, fill=COLOR_TEXT_FOOTER)

        # --- Save Image ---
    # print("正在保存图片...")
    img.save("astrbot_cmds_help.png", format="PNG", optimize=True)
    logger.info(f"已生成命令帮助图片 (尺寸: {img.size[0]}x{img.size[1]})")
