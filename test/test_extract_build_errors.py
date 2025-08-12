import unittest
import textwrap
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the function from the utility file
from src.build_output_analyzer import extract_build_errors  # noqa: E402


class TestBuildErrorAnalyzer(unittest.TestCase):
    """
    Test the extract_build_errors function with realistic build outputs
    from various build tools and languages.
    """

    def test_small_output_returned_as_is(self):
        """Test that small outputs are returned unchanged"""
        small_output = "This is a small error\nOnly two lines"
        result = extract_build_errors(small_output)
        self.assertEqual(result, small_output)

    def test_maven_compilation_errors(self):
        """Test with Maven compilation errors"""
        maven_output = textwrap.dedent("""
            [INFO] Scanning for projects...
            [INFO]
            [INFO] ---------------------< com.example:my-application >---------------------
            [INFO] Building My Application 1.0-SNAPSHOT
            [INFO] --------------------------------[ jar ]---------------------------------
            [INFO]
            [INFO] --- maven-resources-plugin:3.2.0:resources (default-resources) @ my-application ---
            [INFO] Using 'UTF-8' encoding to copy filtered resources.
            [INFO] Copying 1 resource
            [INFO]
            [INFO] --- maven-compiler-plugin:3.8.1:compile (default-compile) @ my-application ---
            [INFO] Compiling 25 source files to /home/runner/work/my-application/target/classes
            [ERROR] /home/runner/work/my-application/src/main/java/com/example/service/UserService.java:[42,35] cannot find symbol
            [ERROR]   symbol:   method validateUserInput(java.lang.String,java.lang.String)
            [ERROR]   location: class com.example.util.ValidationUtils
            [ERROR] /home/runner/work/my-application/src/main/java/com/example/service/UserService.java:[57,16] incompatible types: java.lang.String cannot be converted to boolean
            [INFO] 2 errors
            [ERROR] Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin:3.8.1:compile (default-compile) on project my-application: Compilation failure: Compilation failure:  # noqa: E501
            [ERROR] /home/runner/work/my-application/src/main/java/com/example/service/UserService.java:[42,35] cannot find symbol
            [ERROR]   symbol:   method validateUserInput(java.lang.String,java.lang.String)
            [ERROR]   location: class com.example.util.ValidationUtils
            [ERROR] /home/runner/work/my-application/src/main/java/com/example/service/UserService.java:[57,16] incompatible types: java.lang.String cannot be converted to boolean
            [ERROR] -> [Help 1]
            [ERROR]
            [ERROR] To see the full stack trace of the errors, re-run Maven with the -e switch.
            [ERROR] Re-run Maven using the -X switch to enable full debug logging.
            [ERROR]
            [ERROR] For more information about the errors and possible solutions, please read the following articles:
            [ERROR] [Help 1] http://cwiki.apache.org/confluence/display/MAVEN/MojoFailureException
        """)

        result = extract_build_errors(maven_output)

        # Check that the result contains the key error information
        self.assertIn("[ERROR] /home/runner/work/my-application/src/main/java/com/example/service/UserService.java:[42,35] cannot find symbol", result)
        self.assertIn("Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin", result)
        self.assertIn("[Help 1]", result)

        # The result should group related errors together
        self.assertIn("incompatible types: java.lang.String cannot be converted to boolean", result)

        # Should contain build failure heading
        self.assertIn("BUILD FAILURE - KEY ERRORS:", result)

    def test_gradle_build_errors(self):
        """Test with Gradle build errors"""
        gradle_output = textwrap.dedent("""
            > Configure project :app
            file or directory '/home/runner/work/my-app/app/src/main/assets', not found

            > Task :app:preBuild UP-TO-DATE
            > Task :app:preDebugBuild UP-TO-DATE
            > Task :app:processDebugResources FAILED

            FAILURE: Build failed with an exception.

            * What went wrong:
            Execution failed for task ':app:processDebugResources'.
            > A failure occurred while executing com.android.build.gradle.internal.res.LinkApplicationAndroidResourcesTask$TaskAction
               > Android resource linking failed
                 /home/runner/work/my-app/app/build/intermediates/packaged_manifests/debug/AndroidManifest.xml:25: error: resource style/AppTheme not found.
                 error: failed processing manifest.

            * Try:
            > Run with --stacktrace option to get the stack trace.
            > Run with --info or --debug option to get more log output.
            > Run with --scan to get full insights.

            * Get more help at https://help.gradle.org

            BUILD FAILED in 2m 33s
            35 actionable tasks: 1 executed, 34 up-to-date
        """)

        result = extract_build_errors(gradle_output)

        # Check that the result contains the task that failed
        self.assertIn("> Task :app:processDebugResources FAILED", result)

        # Should include the "What went wrong" section
        self.assertIn("* What went wrong:", result)
        self.assertIn("Android resource linking failed", result)

        # Should include the specific error about missing resource
        self.assertIn("error: resource style/AppTheme not found", result)

        # Should include the help information (context)
        self.assertIn("* Try:", result)

    def test_npm_build_errors(self):
        """Test with NPM build errors"""
        npm_output = textwrap.dedent("""
            > myapp@1.0.0 build
            > webpack --config webpack.config.js

            asset main.js 1.27 MiB [emitted] (name: main)
            runtime modules 1.25 KiB 6 modules
            cacheable modules 615 KiB
              modules by path ./node_modules/ 547 KiB
                modules by path ./node_modules/react-dom/ 131 KiB
                  ./node_modules/react-dom/index.js 1.33 KiB [built] [code generated]
                  ./node_modules/react-dom/client.js 638 bytes [built] [code generated]
              modules by path ./src/ 68.1 KiB
                ./src/index.tsx 926 bytes [built] [code generated]
                ./src/App.tsx + 2 modules 67.2 KiB [built] [code generated]

            ERROR in ./src/components/UserList.tsx:42:19
            Module parse failed: Unexpected token (42:19)
            You may need an appropriate loader to handle this file type, currently no loaders are configured to process this file. See https://webpack.js.org/concepts#loaders
            |
            |     const renderUser = (user: User) => {
            >       return <div key={user.id}>
            |         <span>{user.name}</span>
            |       </div>;

            webpack 5.74.0 compiled with 1 error in 3245 ms

            npm ERR! code ELIFECYCLE
            npm ERR! errno 1
            npm ERR! myapp@1.0.0 build: `webpack --config webpack.config.js`
            npm ERR! Exit status 1
            npm ERR!
            npm ERR! Failed at the myapp@1.0.0 build script.
            npm ERR! This is probably not a problem with npm. There is likely additional logging output above.

            npm ERR! A complete log of this run can be found in:
            npm ERR!     /home/runner/.npm/_logs/2022-10-15T12_34_56_789Z-debug.log
        """)

        result = extract_build_errors(npm_output)

        # Check for webpack error message
        self.assertIn("ERROR in ./src/components/UserList.tsx:42:19", result)
        self.assertIn("Module parse failed: Unexpected token (42:19)", result)

        # Should include the code snippet context
        self.assertIn(">       return <div key={user.id}>", result)

        # Should include the npm error message
        self.assertIn("npm ERR! code ELIFECYCLE", result)
        self.assertIn("npm ERR! Failed at the myapp@1.0.0 build script.", result)

    def test_python_errors(self):
        """Test with Python build/test errors"""
        python_output = textwrap.dedent("""
            ============================= test session starts ==============================
            platform linux -- Python 3.8.10, pytest-6.2.5, py-1.11.0, pluggy-1.0.0
            rootdir: /home/runner/work/my-python-app
            collected 32 items

            tests/test_authentication.py ..                                         [  6%]
            tests/test_utils.py ...                                                 [ 15%]
            tests/test_models.py ...F                                               [ 24%]
            tests/test_api.py .F...                                                [ 40%]
            tests/test_views.py ............                                        [ 76%]
            tests/test_middleware.py ......                                         [ 94%]
            tests/test_integration.py .F                                            [100%]
            =================================== FAILURES ===================================
            _______________________ test_user_creation_validates_email ______________________

            def test_user_creation_validates_email():
                # Test that invalid emails are rejected
                user = User(username='testuser', email='invalid-email')
            >       assert user.is_valid()
            E       AssertionError: assert False
            E        +  where False = <bound method User.is_valid of <User: testuser>>()

            tests/test_models.py:45: AssertionError
            __________________________ test_api_authentication __________________________

            def test_api_authentication():
                # Test that API authentication works
                client = APIClient()
                response = client.post('/api/v1/login', {
                    'username': 'testuser',
                    'password': 'password123'
                })
            >       assert response.status_code == 200
            E       assert 403 == 200
            E        +  where 403 = <Response status_code=403>.status_code

            tests/test_api.py:78: AssertionError
            __________________________ test_integration_workflow __________________________

            def test_integration_workflow():
                # Test the full user registration workflow
                response = client.post('/api/register', {
                    'username': 'newuser',
                    'email': 'newuser@example.com',
                    'password': 'secure-pwd-123'
                })
            >       assert response.status_code == 201
            E       assert 500 == 201
            E        +  where 500 = <Response status_code=500>.status_code

            tests/test_integration.py:23: AssertionError
            ======================= 3 failed, 29 passed in 3.42s =======================
        """)

        result = extract_build_errors(python_output)

        # Check for pytest failure information
        self.assertIn("=================================== FAILURES ===================================", result)

        # Should include the first test failure
        self.assertIn("test_user_creation_validates_email", result)
        self.assertIn("AssertionError: assert False", result)

        # Should include the API test failure
        self.assertIn("test_api_authentication", result)
        self.assertIn("assert 403 == 200", result)

        # Should include the integration test failure
        self.assertIn("test_integration_workflow", result)
        self.assertIn("assert 500 == 201", result)

    def test_multiple_disconnected_errors(self):
        """Test with multiple disconnected errors in different parts of the log"""
        mixed_output = textwrap.dedent("""
            [INFO] Starting build process
            [INFO] Configuring environment
            [ERROR] Configuration error: Missing required value 'api.key' in config.json
            [INFO] Attempting to use default configuration
            [INFO] Running compilation steps
            [INFO] Building module A
            [INFO] Building module B
            [INFO] Building module C
            [ERROR] Failed to compile module C: Syntax error in src/module-c/index.js line 42
            [INFO] Continuing with tests
            [INFO] Running tests for module A
            [INFO] Tests for module A completed successfully
            [INFO] Running tests for module B
            [INFO] Tests for module B completed successfully
            [ERROR] Test failures in module A: 3 tests failed
              - TestCase1: Expected true but got false
              - TestCase2: TypeError: Cannot read property 'value' of undefined
              - TestCase3: Timeout after 5000ms
            [INFO] Build process complete with errors
        """)

        result = extract_build_errors(mixed_output)

        # Check that it finds disconnected errors
        self.assertIn("Configuration error: Missing required value 'api.key' in config.json", result)
        self.assertIn("Failed to compile module C: Syntax error in src/module-c/index.js line 42", result)
        self.assertIn("Test failures in module A: 3 tests failed", result)

        # Check that it includes context around errors
        self.assertIn("[INFO] Attempting to use default configuration", result)  # Line after first error
        self.assertIn("[INFO] Building module C", result)  # Line before second error

    def test_adjacent_errors_merged(self):
        """Test that adjacent errors are properly merged into a single block"""
        adjacent_errors = textwrap.dedent("""
            [INFO] Starting build
            [INFO] Compiling sources
            [ERROR] Error in file A.java: Cannot resolve symbol 'HttpRequest'
            [ERROR] Error in file A.java: Method 'send' not found
            [ERROR] Error in file A.java: Incompatible types: int cannot be converted to String
            [INFO] Build failed
        """)

        result = extract_build_errors(adjacent_errors)

        # Check that all three errors are in a single block
        self.assertIn("Cannot resolve symbol 'HttpRequest'", result)
        self.assertIn("Method 'send' not found", result)
        self.assertIn("Incompatible types: int cannot be converted to String", result)

        # Verify they're not separated by the ... marker that indicates separate blocks
        self.assertNotIn("...\n\n[ERROR] Error in file A.java: Method 'send' not found", result)

    def test_long_stacktrace(self):
        """Test with a long Java stacktrace error"""
        java_stacktrace = textwrap.dedent("""
            > Task :app:compileJava
            > Task :app:processResources
            > Task :app:classes
            > Task :app:run
            Exception in thread "main" java.lang.NullPointerException: Cannot invoke "String.length()" because "input" is null
                at com.example.app.StringProcessor.process(StringProcessor.java:25)
                at com.example.app.Controller.processInput(Controller.java:42)
                at com.example.app.Controller.handleRequest(Controller.java:31)
                at com.example.app.ApiServlet.doPost(ApiServlet.java:57)
                at javax.servlet.http.HttpServlet.service(HttpServlet.java:681)
                at javax.servlet.http.HttpServlet.service(HttpServlet.java:764)
                at org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:227)
                at org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:162)
                at org.apache.tomcat.websocket.server.WsFilter.doFilter(WsFilter.java:53)
                at org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:189)
                at org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:162)
                at org.apache.catalina.core.StandardWrapperValve.invoke(StandardWrapperValve.java:197)
                at org.apache.catalina.core.StandardContextValve.invoke(StandardContextValve.java:97)
                at org.apache.catalina.authenticator.AuthenticatorBase.invoke(AuthenticatorBase.java:541)
                at org.apache.catalina.core.StandardHostValve.invoke(StandardHostValve.java:135)
                at org.apache.catalina.valves.ErrorReportValve.invoke(ErrorReportValve.java:92)
                at org.apache.catalina.core.StandardEngineValve.invoke(StandardEngineValve.java:78)
                at org.apache.catalina.connector.CoyoteAdapter.service(CoyoteAdapter.java:360)
                at org.apache.coyote.http11.Http11Processor.service(Http11Processor.java:399)
                at org.apache.coyote.AbstractProcessorLight.process(AbstractProcessorLight.java:65)
                at org.apache.coyote.AbstractProtocol$ConnectionHandler.process(AbstractProtocol.java:890)
                at org.apache.tomcat.util.net.NioEndpoint$SocketProcessor.doRun(NioEndpoint.java:1789)
                at org.apache.tomcat.util.net.SocketProcessorBase.run(SocketProcessorBase.java:49)
                at org.apache.tomcat.util.threads.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1191)
                at org.apache.tomcat.util.threads.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:659)
                at org.apache.tomcat.util.threads.TaskThread$WrappingRunnable.run(TaskThread.java:61)
                at java.base/java.lang.Thread.run(Thread.java:829)
            > Task :app:run FAILED

            FAILURE: Build failed with an exception.

            * What went wrong:
            Execution failed for task ':app:run'.
            > Process 'command '/usr/lib/jvm/java-11-openjdk/bin/java'' finished with non-zero exit value 1

            * Try:
            > Run with --info or --debug option to get more log output.

            * Exception is:
            org.gradle.process.internal.ExecException: Process 'command '/usr/lib/jvm/java-11-openjdk/bin/java'' finished with non-zero exit value 1
        """)

        result = extract_build_errors(java_stacktrace)

        # Should include the exception message and cause
        self.assertIn("Exception in thread \"main\" java.lang.NullPointerException: Cannot invoke \"String.length()\" because \"input\" is null", result)

        # Should include the important stack frames (application code)
        self.assertIn("at com.example.app.StringProcessor.process(StringProcessor.java:25)", result)
        self.assertIn("at com.example.app.Controller.processInput(Controller.java:42)", result)

        # Should include the Gradle failure message
        self.assertIn("FAILURE: Build failed with an exception.", result)
        self.assertIn("* What went wrong:", result)
        self.assertIn("Process 'command '/usr/lib/jvm/java-11-openjdk/bin/java'' finished with non-zero exit value 1", result)

    def test_no_error_fallback(self):
        """Test the fallback when no error indicators are found"""
        no_error_output = textwrap.dedent("""
            [INFO] This is a very long log
            [INFO] With lots of data
            [INFO] But no actual issue keywords
            [INFO] That the analyzer would detect
            [INFO] So it should fall back to returning
            [INFO] The last portion of the log
            [INFO] Since those lines are most likely
            [INFO] To contain useful content
            [INFO] About why the build might have stopped
            [INFO] Even without explicit markers
            [INFO] This is the end of the log
        """) * 10  # Repeat to ensure it's long enough to trigger truncation

        result = extract_build_errors(no_error_output)

        # Should fall back to returning the last part of the log
        self.assertIn("BUILD FAILURE - LAST OUTPUT:", result)
        self.assertIn("This is the end of the log", result)


if __name__ == '__main__':
    unittest.main()
