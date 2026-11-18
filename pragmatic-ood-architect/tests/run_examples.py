"""编译并运行文档所链接的实际源码。产物仅存在于临时目录。"""
import os
from pathlib import Path
import shutil
from subprocess import run
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def execute(*args):
    run(args, check=True, cwd=ROOT, timeout=60)


if __name__ == '__main__':
    tsc = shutil.which(os.environ.get('TSC', 'tsc'))
    if not tsc:
        raise SystemExit('未找到 tsc；将 TSC 设为已有 TypeScript 编译器的绝对路径。')
    with TemporaryDirectory() as tmp:
        execute('javac', '--release', '17', '-d', tmp, 'examples/code/LockedSetHandle.java',
                'tests/TestLockedSetHandle.java')
        execute('java', '-cp', tmp, 'TestLockedSetHandle')
        print('PASS Java: 独占集合，双线程插入与查询。')
        execute(tsc, '--strict', '--target', 'ES2022', '--module', 'commonjs', '--outDir', tmp,
                'tests/exportable.test.ts', 'examples/code/exportable.ts')
        execute('node', str(Path(tmp) / 'tests/exportable.test.js'))
        print('PASS TS: 合法对象、缺失/错误方法、错误返回值。')
