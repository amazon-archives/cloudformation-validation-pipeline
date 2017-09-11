import os
from setuptools import setup
from setuptools.command.test import test as TestCommand
from setuptools import Command
import subprocess
import sys


def get_data_files(directories):
    build_docs()
    paths = {}
    for directory in directories:
        for (path, directories, filenames) in os.walk(directory):
            for filename in filenames:
                if not path.startswith('code/scripts'):
                    if path not in paths.keys():
                        paths[path] = []
                    paths[path].append(os.path.join(path, filename))
        data_files = []
        for k in paths.keys():
            dest_path = k
            if dest_path.startswith('code/'):
                dest_path = dest_path[len('code/'):]
            if not dest_path.startswith('scripts/'):
                data_files.append(('project-skeleton/validation_pipeline/' + dest_path, paths[k]))
    return data_files


def build_docs(dest_path='code/docs'):
    orig_path = os.getcwd()
    for lib in ['awsclients', 'cfnpipeline', 'logger']:
        sys.path.append('%s/code/lambda_functions/lib/%s' % (orig_path, lib))

    try:
        import pdoc
    except ImportError:
        import pip
        pip.main(['install', 'pdoc'])
        import pdoc

    try:
        import boto3
    except ImportError:
        import pip
        pip.main(['install', 'boto3'])
        import boto3

    try:
        os.mkdir(dest_path)
    except OSError as e:
        if e.errno == 17:
            pass
        else:
            raise

    for lib in ['awsclients', 'cfnpipeline', 'logger']:
        f = open('%s/%s/%s.html' % (orig_path, dest_path, lib), 'w')
        f.write(pdoc.html(lib))
        f.close()


class DocGen(Command):
    user_options = []
    description = 'generate html docs with pdoc'

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    @staticmethod
    def run():
        build_docs('docs')


class CustomTestCommand(TestCommand):
    description = 'run tests'
    user_options = []

    def run_tests(self):
        self._run([sys.executable, '-m', 'unittest', 'discover', '-s', './code/tests'])

    @staticmethod
    def _run(command):
        try:
            subprocess.check_call(command)
        except subprocess.CalledProcessError as error:
            print('Command failed with exit code', error.returncode)
            sys.exit(error.returncode)


setup(
    name="aws_cloudformation_validation_pipeline",
    version="0.0.2",
    author="AWS Solutions Builder",
    author_email="aws-solutions-builder@amazon.com",
    description="Authoring package for AWS CloudFormation Template Validation Pipeline",
    license="Amazon Software License 1.0",
    keywords="cloudformation cicd aws pipeline",
    url="https://github.com/awslabs/aws_cloudformation_validation_pipeline/",
    scripts=[
        'code/scripts/cfn-validation-pipeline-skeleton',
        'code/scripts/cfn-validation-pipeline-deploy',
        'code/scripts/cfn-validation-pipeline-cleanup',
        'code/scripts/cfn-validation-pipeline-rollback'
    ],
    data_files=get_data_files(
        [
            'code',
            'cloudformation',
            'demo_source'
        ]
    ),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 2.7",
        "Natural Language :: English",
        "Operating System :: POSIX :: Linux",
        "Topic :: Software Development :: Testing",
        "Environment :: Console",
        "Intended Audience :: Information Technology",
        "License :: Amazon Software License :: 1.0",
    ],
    zip_safe=False,
    setup_requires=[
        'pdoc'
    ],
    install_requires=[
        'boto3'
    ],
    tests_require=[
        'six',
        'mock',
        'boto3',
        'pyyaml'
    ],
    cmdclass={
        'test': CustomTestCommand,
        'build_docs': DocGen
    }
)