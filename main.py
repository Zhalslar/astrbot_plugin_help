from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star_handler import star_handlers_registry, StarHandlerMetadata


@register("helloworld", "YourName", "一个简单的 Hello World 插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""

    @filter.command("helps", alias={"帮助", "使用方法"})
    async def get_help(self, event: AstrMessageEvent) -> MessageEventResult:
        """获取插件帮助信息"""
        yield event.plain_result(self.get_all_commands())

    def get_all_commands(self) -> str:
        """获取插件所有的命令列表"""
        command_handlers = []
        command_names = []
        try:
            all_stars_metadata = self.context.get_all_stars()
        except Exception as e:
            logger.error(f"获取插件列表失败: {e}")
            return []

        if not all_stars_metadata:
            logger.warning("没有找到任何插件")
            return []

        for star in all_stars_metadata:
            plugin_name = getattr(star, "name", "未知插件")
            plugin_instance = getattr(star, "star_cls", None)

            if not plugin_name or not isinstance(plugin_instance, Star):
                logger.warning(f"插件 {plugin_name} 的实例无效")
                continue

            # 检查插件实例是否是当前插件的实例
            if plugin_instance is self:
                continue
            # 获取插件的所有命令
            for handler in star_handlers_registry:
                assert isinstance(handler, StarHandlerMetadata)
                if handler.handler_module_path != star.module_path:
                    continue
                for filter_ in handler.event_filters:
                    if isinstance(filter_, CommandFilter):
                        command_handlers.append(handler)
                        command_names.append(filter_.command_name)
                        break
                    elif isinstance(filter_, CommandGroupFilter):
                        command_handlers.append(handler)
                        command_names.append(filter_.group_name)
        help_msg = ""
        if len(command_handlers) > 0:
            for i in range(len(command_handlers)):
                help_msg += f'- {command_names[i]}'
                if command_handlers[i].desc:
                    help_msg += f" :  {command_handlers[i].desc}"
                help_msg += "\n"
        return help_msg